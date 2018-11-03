# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime as DateTime
from email.message import Message
import email.utils

from .app_helpers import init_app, init_smtp_mailer
from .message_handler import MessageHandler
from .queue_runner import enqueue_message


__all__ = ['build_check_message', 'send_test_message']

def build_check_message(recipient, sender=None):
    mail = Message()
    sender = sender or recipient
    mail['From'] = sender
    mail['To'] = recipient
    mail['Date'] = email.utils.format_datetime(DateTime.now())
    # if no domain is specified for ".make_msgid()" the function can take
    # a long time in case "socket.getfqdn()" must make some network
    # requests (e.g. flaky network connection).
    mail['Message-ID'] = email.utils.make_msgid(domain='mqrunner.example')
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
    msg_path = enqueue_message(msg, queue_path, sender=msg_sender, recipient=recipient)

    mh = MessageHandler(mailer)
    was_sent = mh.send_message(msg_path)
    return was_sent

