# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO
import logging

from .message_utils import dt_now, msg_as_bytes, MsgInfo, SendResult
from .plugins import MQAction, MQSignal


__all__ = ['BaseMsg', 'InMemoryMsg', 'MessageHandler']

class MessageHandler(object):
    def __init__(self, transports, delivery_log=None, plugins=None):
        self.transports = transports
        self.delivery_log = delivery_log or logging.getLogger('mailqueue.delivery_log')
        self.plugins = plugins

    def send_message(self, msg, **kwargs):
        msg_wrapper = self._wrap_msg(msg)
        result = msg_wrapper.start_delivery()
        if not result:
            return None
        sender, recipients = self._msg_metadata(msg_wrapper, **kwargs)
        if msg_wrapper.from_addr is None:
            msg_wrapper.from_addr = sender
        if msg_wrapper.to_addrs is None:
            msg_wrapper.to_addrs = recipients
        msg_bytes = msg_wrapper.msg_bytes

        send_result = SendResult(False)
        for transport in self.transports:
            send_result = transport.send(sender, recipients, msg_bytes)
            if (send_result is True) or (send_result is False):
                send_result = SendResult(send_result)
            if send_result:
                self._notify_plugins(MQSignal.delivery_successful, msg_wrapper, send_result)
                msg_wrapper.delivery_successful()
                was_queued = (send_result.queued is not False)
                if not was_queued:
                    self._log_successful_delivery(msg_wrapper, sender, recipients)
                break

        if not send_result:
            msg_wrapper.retries += 1
            msg_wrapper.last_delivery_attempt = dt_now()
            discard_message = self._notify_plugins(MQSignal.delivery_failed, msg_wrapper, send_result)
            msg_wrapper.delivery_failed(discard=discard_message)
            send_result.discarded = discard_message
        return send_result

    # --- internal functionality ----------------------------------------------
    def _log_successful_delivery(self, msg, sender, recipients):
        log_msg = '%s => %s' % (sender, ', '.join(recipients))
        if msg.msg_id:
            log_msg += ' <%s>' % msg.msg_id
        self.delivery_log.info(log_msg)

    def _notify_plugins(self, signal, msg, send_result):
        if self.plugins is None:
            return
        results = self.plugins.call_plugins(signal, signal_kwargs={'msg': msg, 'send_result': send_result})

        if not results:
            return None
        decisions = set()
        for handler, result in results:
            if result is not None:
                decisions.add(result)
        discard_message = (MQAction.DISCARD in decisions)
        return discard_message

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
        recipients = kwargs.pop('recipients', None)
        if recipient and recipients:
            raise ValueError('__init__() got conflicting parameters: recipient=%r, recipients=%r' % (recipient, recipients))
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
    def __init__(self):
        self._from = None
        self._to_addrs = None
        self._retries = None
        self._last = None


    def start_delivery(self):
        raise NotImplementedError('subclasses must override this method')

    def delivery_failed(self, discard=False):
        pass

    def delivery_successful(self):
        pass

    @property
    def from_addr(self):
        if self._from is not None:
            return self._from
        return self.msg.from_addr

    @from_addr.setter
    def from_addr(self, value):
        self._from = value

    @property
    def to_addrs(self):
        if self._to_addrs is not None:
            return self._to_addrs
        return self.msg.to_addrs

    @to_addrs.setter
    def to_addrs(self, value):
        self._to_addrs = value

    @property
    def msg_bytes(self):
        return self.msg.msg_bytes

    @property
    def msg_id(self):
        return self.msg.msg_id

    @property
    def retries(self):
        return self._retries or 0

    @retries.setter
    def retries(self, value):
        self._retries = value



class InMemoryMsg(BaseMsg):
    def __init__(self, from_addr, to_addrs, msg_bytes):
        super(InMemoryMsg, self).__init__()
        msg_fp = BytesIO(msg_as_bytes(msg_bytes))
        self.msg = MsgInfo(from_addr, to_addrs, msg_fp)

    def start_delivery(self):
        return True

