# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO
import logging
import os

from .compat import IS_WINDOWS
from .maildir_utils import move_message
from .message_utils import msg_as_bytes, parse_message_envelope, MsgInfo


__all__ = ['MessageHandler']

class MessageHandler(object):
    def __init__(self, transports, delivery_log=None):
        self.transports = transports
        self.delivery_log = delivery_log or logging.getLogger('mailqueue.delivery_log')

    def send_message(self, msg, **kwargs):
        msg_wrapper = self._wrap_msg(msg)
        result = msg_wrapper.start_delivery()
        if not result:
            return None
        sender, recipients = self._msg_metadata(msg_wrapper, **kwargs)
        msg_bytes = msg_wrapper.msg_bytes

        was_sent = False
        for transport in self.transports:
            was_sent = transport.send(sender, recipients, msg_bytes)
            if was_sent:
                msg_wrapper.delivery_successful()
                self._log_successful_delivery(msg_wrapper, sender, recipients)
                break
        if not was_sent:
            msg_wrapper.delivery_failed()
            return False
        return True

    # --- internal functionality ----------------------------------------------
    def _log_successful_delivery(self, msg, sender, recipients):
        log_msg = '%s => %s' % (sender, ', '.join(recipients))
        if msg.msg_id:
            log_msg += ' <%s>' % msg.msg_id
        self.delivery_log.info(log_msg)

    def _wrap_msg(self, msg):
        if hasattr(msg, 'start_delivery'):
            return msg
        msg_bytes = msg_as_bytes(msg)
        return InMemoryMsg(None, None, msg_bytes)

    def _msg_metadata(self, msg, **kwargs):
        sender = kwargs.pop('sender', None)
        if not sender:
            sender = msg.from_addr

        recipient = kwargs.pop('recipient', None)
        recipients = None
        if recipient:
            recipients = (recipient,)
        if not recipients:
            recipients = msg.to_addrs

        if not sender:
            raise ValueError('__init__(): missing keyword parameter "sender"')
        if not recipients:
            raise ValueError('__init__(): missing keyword parameter "recipient"')
        if kwargs:
            extra_name = tuple(kwargs)[0]
            raise TypeError("__init__() got an unexpected keyword argument '%s'" % extra_name)
        return (sender, recipients)



class BaseMsg(object):
    def start_delivery(self):
        raise NotImplementedError('subclasses must override this method')

    def delivery_failed(self):
        pass

    def delivery_successful(self):
        pass

    @property
    def from_addr(self):
        return self.msg.from_addr

    @property
    def to_addrs(self):
        return self.msg.to_addrs

    @property
    def msg_bytes(self):
        return self.msg.msg_bytes

    @property
    def msg_id(self):
        return self.msg.msg_id


class InMemoryMsg(BaseMsg):
    def __init__(self, from_addr, to_addrs, msg_bytes):
        msg_fp = BytesIO(msg_as_bytes(msg_bytes))
        self.msg = MsgInfo(from_addr, to_addrs, msg_fp)

    def start_delivery(self):
        return True



class MaildirBackedMsg(object):
    def __init__(self, file_path):
        self.file_path = file_path
        self.fp = None
        self._msg = None

    def start_delivery(self):
        self.fp = self._mark_message_as_in_progress(self.file_path)
        if self.fp is None:
            # e.g. invalid path
            return None
        return True

    def delivery_failed(self):
        self._move_message_back_to_new(self.fp)

    def delivery_successful(self):
        self._remove_message(self.fp)

    @property
    def msg(self):
        if self._msg is None:
            self._msg = parse_message_envelope(self.fp)
        return self._msg

    @property
    def path(self):
        return self.file_path

    @property
    def from_addr(self):
        return self.msg.from_addr

    @property
    def to_addrs(self):
        return self.msg.to_addrs

    @property
    def msg_bytes(self):
        return self.msg.msg_bytes

    @property
    def msg_id(self):
        return self.msg.msg_id

    # --- internal helpers ----------------------------------------------------
    def _mark_message_as_in_progress(self, source_path):
        return move_message(source_path, target_folder='cur')

    def _move_message_back_to_new(self, fp):
        if IS_WINDOWS:
            fp.close()
        move_message(fp, target_folder='new', open_file=False)
        if not IS_WINDOWS:
            # this ensures all locks will be released and we don't keep open files
            # around for no reason.
            fp.close()

    def _remove_message(self, fp):
        file_path = fp.name
        if IS_WINDOWS:
            # On Windows we can not unlink files while they are opened. Keep
            # the file open on Linux until after the unlink to keep the lock on
            # that file until everything is done (to prevent concurrent access).
            fp.close()
        try:
            os.unlink(file_path)
        except OSError:
            pass
        if not IS_WINDOWS:
            # This will also release the lock
            fp.close()

