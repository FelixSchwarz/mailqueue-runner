# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import email.utils
from datetime import datetime as DateTime
from email.message import Message

from boltons.timeutils import LocalTZ

from .app_helpers import init_app, init_smtp_mailer
from .message_handler import InMemoryMsg, MessageHandler
from .message_utils import msg_as_bytes


__all__ = ['send_test_message']

def _build_check_message(recipient: str, sender: str) -> Message:
    mail = Message()
    mail['From'] = sender
    mail['To'] = recipient
    now = DateTime.now(tz=LocalTZ)
    mail['Date'] = email.utils.format_datetime(now)
    # if no domain is specified for ".make_msgid()" the function can take
    # a long time in case "socket.getfqdn()" must make some network
    # requests (e.g. flaky network connection).
    mail['Message-ID'] = email.utils.make_msgid(domain='mqrunner.example')
    mail['Subject'] = 'Test message from mailqueue-runner'
    mail.set_payload('This is a test message was generated to test your mailqueue delivery.')
    return mail


def send_test_message(config_path, options):
    sender = options['sender']
    recipient = options['recipient']

    settings = init_app(config_path, options=options)
    if not sender:
        sender = settings.get('from') or recipient
    mailer = init_smtp_mailer(settings)

    check_msg = _build_check_message(recipient, sender=sender)
    msg_sender = check_msg['From']
    msg_bytes = msg_as_bytes(check_msg)
    msg = InMemoryMsg(msg_sender, (recipient,), msg_bytes)

    # The idea of sending a test message is to provide immediate feedback so
    # we use the SMTP transport only even when a queue directory might be set
    # in the configuration file.
    mh = MessageHandler(transports=(mailer,))
    was_sent = mh.send_message(msg)
    return was_sent
