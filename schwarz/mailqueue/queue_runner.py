# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import logging
from mailbox import Maildir
import os
import time

from .app_helpers import init_app, init_smtp_mailer
from .compat import queue, FileNotFoundError, IS_WINDOWS
from .maildir_utils import move_message
from .message_handler import MessageHandler
from .message_utils import msg_as_bytes, parse_message_envelope, SendResult


__all__ = [
    'enqueue_message',
    'send_all_queued_messages',
    'MaildirBackend',
]

def enqueue_message(msg, queue_path, sender, recipients, return_msg=False):
    msg_bytes = serialize_message_with_queue_data(msg, sender=sender, recipients=recipients)
    mailbox = Maildir(queue_path)
    unique_id = mailbox.add(msg_bytes)
    msg_path = os.path.join(queue_path, 'new', unique_id)
    if return_msg:
        return MaildirBackedMsg(msg_path)
    return msg_path


def serialize_message_with_queue_data(msg, sender, recipients):
    sender_bytes = _email_address_as_bytes(sender)
    b_recipients = [_email_address_as_bytes(recipient) for recipient in recipients]
    queue_bytes = b'\n'.join([
        b'Return-path: <' + sender_bytes + b'>',
        b'Envelope-to: ' + b','.join(b_recipients),
        msg_as_bytes(msg)
    ])
    return queue_bytes

def _email_address_as_bytes(address):
    if isinstance(address, bytes):
        return address
    # LATER: support non-ascii addresses
    return address.encode('ascii')



class MaildirBackend(object):
    def __init__(self, queue_path):
        self.queue_path = queue_path

    def send(self, from_addr, to_addrs, msg_bytes):
        enqueue_message(msg_bytes, self.queue_path, from_addr, to_addrs)
        return SendResult(True, queued=True, transport='maildir')



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



def is_stale_msg(msg_path):
    stat = os.stat(msg_path)
    # Unix:
    #  - mtime: last modification of file contents
    #  - ctime: last modification of file metadata
    # Windows:
    #  - ctime: file creation
    timestamp = max([stat.st_mtime, stat.st_ctime])
    now = time.time()
    STALE_TIMEOUT_s = 30 * 60
    is_stale = (timestamp + STALE_TIMEOUT_s < now)
    return is_stale

def unblock_stale_messages(queue_basedir, log):
    path_cur = os.path.join(queue_basedir, 'cur')
    try:
        filenames = os.listdir(path_cur)
    except FileNotFoundError:
        log.error('Queue directory %s does not exist.', path_cur)
        return
    for filename in filenames:
        msg_path = os.path.join(path_cur, filename)
        if is_stale_msg(msg_path):
            log.warning('stale message detected, moving back to "new": %s', filename)
            move_message(msg_path, target_folder='new', open_file=False)

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
    unblock_stale_messages(queue_dir, log)
    message_queue = find_new_messsages(queue_dir, log)
    if message_queue.qsize() == 0:
        log.info('no unsent messages in queue dir')
        return
    log.debug('%d unsent messages in queue dir', message_queue.qsize())
    mh = MessageHandler([mailer])
    while True:
        try:
            message_path = message_queue.get(block=False)
        except queue.Empty:
            break
        else:
            msg = MaildirBackedMsg(message_path)
            mh.send_message(msg)

# --------------------------------------------

def one_shot_queue_run(queue_dir, config_path, options=None):
    settings = init_app(config_path, options=options)
    mailer = init_smtp_mailer(settings)
    send_all_queued_messages(queue_dir, mailer)

