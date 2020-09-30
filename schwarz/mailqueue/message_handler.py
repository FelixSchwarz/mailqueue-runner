# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import logging
import os

from .compat import IS_WINDOWS
from .maildir_utils import move_message
from .message_utils import parse_message_envelope


__all__ = ['MessageHandler']

class MessageHandler(object):
    def __init__(self, mailer, delivery_log=None):
        self.mailer = mailer
        self.delivery_log = delivery_log or logging.getLogger('mailqueue.delivery_log')

    def send_message(self, file_path):
        fp = self._mark_message_as_in_progress(file_path)
        if fp is None:
            # e.g. invalid path
            return None
        msg = parse_message_envelope(fp)
        was_sent = self.mailer.send(msg.from_addr, msg.to_addrs, msg.msg_bytes)
        if was_sent:
            self._remove_message(fp)
            self._log_successful_delivery(msg)
        else:
            self._move_message_back_to_new(fp)
        return was_sent

    # --- internal functionality ----------------------------------------------
    def _log_successful_delivery(self, msg):
        log_msg = '%s => %s' % (msg.from_addr, ', '.join(msg.to_addrs))
        if msg.msg_id:
            log_msg += ' <%s>' % msg.msg_id
        self.delivery_log.info(log_msg)

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

