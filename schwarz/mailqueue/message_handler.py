# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

from schwarz.mailqueue.delivery_log import DeliveryEvent, format_delay, format_logfmt, format_smtp_response

from .message_utils import MsgInfo, SendResult, dt_now, msg_as_bytes
from .plugins import MQAction, MQSignal


if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime as DateTime

    from schwarz.puzzle_plugins import SignalRegistry

    from schwarz.mailqueue.message_utils import Transport


__all__ = ['BaseMsg', 'InMemoryMsg', 'MessageHandler']

@dataclass(frozen=True)
class _LogInfo:
    """Information about a message which is needed for logging after the delivery attempt."""
    from_addr: str
    to: str
    msgid: str | None
    is_in_queue: bool
    waited_in_queue: bool
    attempt: int
    queue_date: DateTime | None

    @classmethod
    def from_msg(cls, msg: BaseMsg, sender: str, recipients: Sequence[str]) -> _LogInfo:
        return cls(
            from_addr       = sender,
            to              = ','.join(recipients),
            msgid           = msg.msg_id,
            is_in_queue     = msg.is_in_queue,
            waited_in_queue = msg.waited_in_queue,
            attempt         = msg.retries + 1,
            queue_date      = getattr(msg, 'queue_date', None),
        )

class MessageHandler:
    def __init__(
        self,
        transports: Sequence[Transport],
        delivery_log: logging.Logger | None = None,
        plugins: SignalRegistry | None = None,
        queue_log: logging.Logger | None = None,
        app: str | None = None,
    ):
        self.transports = transports
        self.delivery_log = delivery_log or logging.getLogger('mailqueue.delivery_log')
        self.queue_log = queue_log or logging.getLogger('mailqueue.queue_log')
        self.plugins = plugins
        # name of the application (e.g. "mq-sendmail"), only used for logging
        self.app = app

    def send_message(self, msg, **kwargs) -> SendResult | None:
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
        # The message file might be moved or deleted after the delivery attempt
        # so we need to collect all information for logging beforehand.
        log_info = _LogInfo.from_msg(msg_wrapper, sender, recipients)

        send_result = SendResult(False)
        failed_result = None
        for transport in self.transports:
            send_result = transport.send(sender, recipients, msg_bytes)
            if (send_result is True) or (send_result is False):
                send_result = SendResult(send_result)
            if send_result:
                self._notify_plugins(MQSignal.delivery_successful, msg_wrapper, send_result)
                msg_wrapper.delivery_successful()
                was_queued = (send_result.queued is not False)
                status = 'queued' if was_queued else 'sent'
                self._log_delivery(status, log_info, send_result, failed_result=failed_result)
                break
            failed_result = send_result

        if not send_result:
            msg_wrapper.retries += 1
            msg_wrapper.last_delivery_attempt = dt_now()
            discard_message = self._notify_plugins(MQSignal.delivery_failed, msg_wrapper, send_result)
            msg_wrapper.delivery_failed(discard=discard_message)
            send_result.discarded = discard_message
            if discard_message:
                status = 'discarded'
            elif log_info.is_in_queue:
                status = 'deferred'
            else:
                status = 'failed'
            self._log_delivery(status, log_info, send_result)
        return send_result

    # --- internal functionality ----------------------------------------------
    def _log_delivery(
        self,
        status: str,
        log_info: _LogInfo,
        send_result: SendResult,
        failed_result: SendResult | None = None,
    ) -> None:
        transport = send_result.transport
        host = send_result.host
        delay = None
        if log_info.waited_in_queue and log_info.queue_date:
            delay = format_delay(dt_now() - log_info.queue_date)
        # "queued" messages: show why the previous transport failed
        details = send_result
        if not _has_details(send_result) and (failed_result is not None):
            details = failed_result
        smtp_response = details.smtp_response
        event = DeliveryEvent(
            status    = status,
            to        = log_info.to,
            msgid     = log_info.msgid,
            via       = f'{transport}:{host}' if (transport and host) else transport,
            from_addr = log_info.from_addr,
            attempts  = log_info.attempt if log_info.waited_in_queue else None,
            delay     = delay,
            app       = self.app,
            smtp      = format_smtp_response(smtp_response) if (smtp_response is not None) else None,
            error     = details.error if (smtp_response is None) else None,
        )

        log_line = format_logfmt(event)
        extra = {'delivery': event.as_dict()}
        self.delivery_log.info(log_line, extra=extra)
        # The queue log shows the history of all messages which could not be
        # delivered immediately (but not messages which were only stored
        # temporarily before a successful delivery).
        if (status == 'queued') or (log_info.is_in_queue and (log_info.waited_in_queue or status != 'sent')):
            self.queue_log.info(log_line, extra=extra)

    def _notify_plugins(self, signal, msg, send_result):
        if self.plugins is None:
            return
        signal_kwargs = {'msg': msg, 'send_result': send_result}
        results = self.plugins.call_plugins(signal, signal_kwargs=signal_kwargs)

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
            raise ValueError('__init__() got conflicting parameters: recipient=%r, recipients=%r' % (recipient, recipients))  # noqa: E501 (line too long)
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



class BaseMsg:
    def __init__(self, msg: MsgInfo | None = None):
        self._msg = msg
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
    def msg(self):
        return self._msg

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

    @property
    def is_in_queue(self):
        """True if the message is stored in the queue (also while it is sent)."""
        return False

    @property
    def waited_in_queue(self):
        """True if the message was waiting in the queue for delivery."""
        return False



class InMemoryMsg(BaseMsg):
    def __init__(self, from_addr, to_addrs, msg_bytes: bytes):
        msg_fp = BytesIO(msg_bytes)
        msg = MsgInfo(from_addr, to_addrs, msg_fp)
        super().__init__(msg=msg)

    def start_delivery(self):
        return True


def _has_details(send_result: SendResult) -> bool:
    return (send_result.smtp_response is not None) or (send_result.error is not None)
