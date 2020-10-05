# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime as DateTime
from email.message import Message

from boltons.timeutils import LocalTZ

from .app_helpers import init_app, init_smtp_mailer
from .compat import format_datetime_rfc2822, make_msgid
from .message_handler import MaildirBackedMsg, MessageHandler
from .queue_runner import enqueue_message


__all__ = ['build_check_message', 'send_test_message']

def build_check_message(recipient, sender=None):
    mail = Message()
    sender = sender or recipient
    mail['From'] = sender
    mail['To'] = recipient
    now = DateTime.now(tz=LocalTZ)
    mail['Date'] = format_datetime_rfc2822(now)
    # if no domain is specified for ".make_msgid()" the function can take
    # a long time in case "socket.getfqdn()" must make some network
    # requests (e.g. flaky network connection).
    mail['Message-ID'] = make_msgid(domain='mqrunner.example')
    mail['Subject'] = 'Test message from mailqueue-runner'
    mail.set_payload('This is a test message was generated to test your mailqueue delivery.')
    return mail


def send_test_message(queue_path, config_path, options):
    sender = options['sender']
    recipient = options['recipient']

    settings = init_app(config_path, options=options)
    mailer = init_smtp_mailer(settings)

    msg = build_check_message(recipient, sender=sender)
    msg_sender = msg['From']
    msg_path = enqueue_message(msg, queue_path, sender=msg_sender, recipients=(recipient,))

    _msg = MaildirBackedMsg(msg_path)
    mh = MessageHandler(transports=(mailer,))
    was_sent = mh.send_message(_msg)
    return was_sent

