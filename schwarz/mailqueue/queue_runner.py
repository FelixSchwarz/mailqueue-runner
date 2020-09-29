# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import logging
from mailbox import Maildir
import os

from .app_helpers import init_app, init_smtp_mailer
from .compat import queue, FileNotFoundError
from .message_handler import MessageHandler


__all__ = [
    'enqueue_message',
    'find_new_messsages',
    'send_all_queued_messages',
]

def enqueue_message(msg, queue_path, sender, recipient):
    msg_bytes = serialize_message_with_queue_data(msg, sender=sender, recipient=recipient)
    mailbox = Maildir(queue_path)
    unique_id = mailbox.add(msg_bytes)
    return os.path.join(queue_path, 'new', unique_id)

def serialize_message_with_queue_data(msg, sender, recipient):
    sender_bytes = _email_address_as_bytes(sender)
    recipient_bytes = _email_address_as_bytes(recipient)
    queue_bytes = b'\n'.join([
        b'Return-path: <' + sender_bytes + b'>',
        b'Envelope-to: ' + recipient_bytes,
        _msg_as_bytes(msg)
    ])
    return queue_bytes

def _email_address_as_bytes(address):
    if isinstance(address, bytes):
        return address
    # LATER: support non-ascii addresses
    return address.encode('ascii')

def _msg_as_bytes(msg):
    if hasattr(msg, 'as_bytes'):
        msg_bytes = msg.as_bytes()
    elif hasattr(msg, 'read'):
        msg_bytes = msg.read()
    elif hasattr(msg, 'as_string'):
        # email.message.Message in Python 2
        msg_bytes = msg.as_string().encode('ascii')
    else:
        msg_bytes = msg
    return msg_bytes

def find_new_messsages(queue_basedir, log):
    message_queue = queue.Queue()
    path_new = os.path.join(queue_basedir, 'new')
    try:
        filenames = os.listdir(path_new)
    except FileNotFoundError:
        log.error('Queue directory %s does not exist.', path_new)
    else:
        for filename in filenames:
            path = os.path.join(path_new, filename)
            message_queue.put(path)
    return message_queue

def send_all_queued_messages(queue_dir, mailer):
    log = logging.getLogger('mailqueue.sending')
    message_queue = find_new_messsages(queue_dir, log)
    if message_queue.qsize() == 0:
        log.info('no unsent messages in queue dir')
        return
    log.debug('%d unsent messages in queue dir', message_queue.qsize())
    mh = MessageHandler(mailer)
    while True:
        try:
            message_path = message_queue.get(block=False)
        except queue.Empty:
            break
        else:
            mh.send_message(message_path)

# --------------------------------------------

def one_shot_queue_run(queue_dir, config_path, options=None):
    settings = init_app(config_path, options=options)
    mailer = init_smtp_mailer(settings)
    send_all_queued_messages(queue_dir, mailer)

