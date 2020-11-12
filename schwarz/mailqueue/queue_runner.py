# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import email.utils
import logging
from mailbox import _sync_close, Maildir
import os
import time

from boltons.timeutils import dt_to_timestamp

from .app_helpers import init_app, init_smtp_mailer
from .compat import queue, IS_WINDOWS
from .maildir_utils import create_maildir_directories, find_messages, move_message
from .message_handler import BaseMsg, MessageHandler
from .message_utils import dt_now, msg_as_bytes, parse_message_envelope, SendResult
from .plugins import registry


__all__ = [
    'enqueue_message',
    'send_all_queued_messages',
    'serialize_message_with_queue_data',
    'MaildirBackend',
]

def enqueue_message(msg, queue_path, sender, recipients, return_msg=False, in_progress=False, **queue_args):
    msg_bytes = serialize_message_with_queue_data(msg, sender=sender, recipients=recipients, **queue_args)
    create_maildir_directories(queue_path)

    mailbox = Maildir(queue_path)
    sub_dir = 'cur' if in_progress else 'new'
    return inject_message_into_maildir(msg_bytes, mailbox, sub_dir=sub_dir, return_msg=return_msg)


def inject_message_into_maildir(msg_bytes, maildir, sub_dir='new', return_msg=False):
    tmp_fp = maildir._create_tmp()
    try:
        maildir._dump_message(msg_bytes, tmp_fp)
    except:
        tmp_fp.close()
        os.remove(tmp_fp.name)
        raise
    _sync_close(tmp_fp)
    open_file = bool(return_msg)
    target_ = move_message(tmp_fp, target_folder=sub_dir, open_file=open_file)
    if not return_msg:
        return target_
    return MaildirBackedMsg(target_.name, fp=target_)


def serialize_message_with_queue_data(msg, sender, recipients, queue_date=None, last=None, retries=None):
    sender_bytes = _email_address_as_bytes(sender)
    b_recipients = [_email_address_as_bytes(recipient) for recipient in recipients]
    queue_lines = [
        b'Return-path: <' + sender_bytes + b'>',
        b'Envelope-to: ' + b','.join(b_recipients),
        b'X-Queue-Date: ' + _dt_to_str(queue_date or dt_now()).encode('ASCII'),
    ]
    if last:
        last_attempt_b = b'X-Last-Attempt: ' + _dt_to_str(last).encode('ASCII')
        queue_lines.append(last_attempt_b)
    if retries:
        retries_b = b'X-Retries: ' + str(retries).encode('ASCII')
        queue_lines.append(retries_b)
    queue_lines.extend([
        b'X-Queue-Meta-End: end',
        msg_as_bytes(msg)
    ])
    queue_bytes = b'\n'.join(queue_lines)
    return queue_bytes

def _email_address_as_bytes(address):
    if isinstance(address, bytes):
        return address
    # LATER: support non-ascii addresses
    return address.encode('ascii')

def _dt_to_str(dt):
    if hasattr(email.utils, 'format_datetime'):
        # Python 3.3+
        return email.utils.format_datetime(dt)
    # (Python 2)
    # localtime=True means formatdate() will not convert the DateTime instance
    # to UTC timezone but use the provided timezone.
    return email.utils.formatdate(dt_to_timestamp(dt), localtime=True)



class MaildirBackend(object):
    def __init__(self, queue_path, log=None):
        self.queue_path = queue_path
        self.log = log or logging.getLogger('mailqueue.queue_log')

    def send(self, from_addr, to_addrs, msg_bytes):
        msg = enqueue_message(msg_bytes, self.queue_path, from_addr, to_addrs, return_msg=True)
        log_msg = '%s => %s' % (from_addr, ', '.join(to_addrs))
        if msg.msg_id:
            log_msg += ' <%s>' % msg.msg_id
        self.log.info(log_msg)
        return SendResult(True, queued=True, transport='maildir')



class MaildirBackedMsg(BaseMsg):
    def __init__(self, file_path, fp=None):
        super(MaildirBackedMsg, self).__init__()
        self.file_path = file_path
        self.fp = fp
        self._msg = None

    def start_delivery(self):
        self.fp = self._mark_message_as_in_progress()
        if self.fp is None:
            # e.g. invalid path
            return None
        return True

    def delivery_failed(self, discard=False):
        if discard:
            self._delete_message(self.fp)
            return

        msg_bytes = self.msg_bytes
        queue_bytes = serialize_message_with_queue_data(
            msg_bytes,
            self.from_addr,
            self.to_addrs,
            queue_date = self.queue_date,
            last       = self.last_delivery_attempt,
            retries    = self.retries,
        )
        self.fp.seek(0)
        self.fp.write(queue_bytes)
        self.fp.truncate()
        self.fp.seek(0)
        self._msg = None
        self._move_message_back_to_new()

    def delivery_successful(self):
        self._remove_message(self.fp)

    @property
    def msg(self):
        if self._msg is None:
            if self.fp is None:
                fp = open(self.file_path, 'rb')
                close_fp = True
            else:
                fp = self.fp
                close_fp = False
            try:
                self._msg = parse_message_envelope(fp)
            finally:
                if close_fp:
                    fp.close()
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

    @property
    def queue_date(self):
        return self.msg.queue_date

    @property
    def last_delivery_attempt(self):
        if self._last is not None:
            return self._last
        return self.msg.last

    @last_delivery_attempt.setter
    def last_delivery_attempt(self, value):
        self._last = value

    @property
    def retries(self):
        if self._retries is not None:
            return self._retries
        return self.msg.retries

    @retries.setter
    def retries(self, value):
        self._retries = value

    # --- internal helpers ----------------------------------------------------
    def _mark_message_as_in_progress(self):
        return move_message(self.fp or self.file_path, target_folder='cur')

    def _delete_message(self, fp):
        if IS_WINDOWS:
            fp.close()
        file_path = fp if (not hasattr(fp, 'name')) else fp.name
        os.unlink(file_path)

    def _move_message_back_to_new(self):
        if IS_WINDOWS:
            self.fp.close()
        move_message(self.fp, target_folder='new', open_file=False)
        if not IS_WINDOWS:
            # this ensures all locks will be released and we don't keep open files
            # around for no reason.
            self.fp.close()
        self.fp = None

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
    for msg_path in find_messages(queue_basedir, queue_folder='cur', log=log):
        if is_stale_msg(msg_path):
            filename = os.path.basename(msg_path)
            log.warning('stale message detected, moving back to "new": %s', filename)
            move_message(msg_path, target_folder='new', open_file=False)

def assemble_queue_with_new_messages(queue_basedir, log):
    message_queue = queue.Queue()
    for path in find_messages(queue_basedir, queue_folder='new', log=log):
        message_queue.put(path)
    return message_queue

def send_all_queued_messages(queue_dir, mailer=None, plugins=None, mh=None):
    assert (mailer is None) ^ (mh is None)
    log = logging.getLogger('mailqueue.sending')
    unblock_stale_messages(queue_dir, log)
    message_queue = assemble_queue_with_new_messages(queue_dir, log)
    if message_queue.qsize() == 0:
        log.info('no unsent messages in queue dir')
        return
    log.debug('%d unsent messages in queue dir', message_queue.qsize())
    if mh is None:
        mh = MessageHandler([mailer], plugins=plugins)
    while True:
        try:
            message_path = message_queue.get(block=False)
        except queue.Empty:
            break
        else:
            msg = MaildirBackedMsg(message_path)
            mh.send_message(msg)

# --------------------------------------------

def one_shot_queue_run(queue_dir, config_path=None, options=None, settings=None):
    # ability to pass "settings" so callers can use a custom configuration
    # mechanism (including ability to inject preconfigured MessageHandler).
    assert (config_path is not None) ^ (settings is not None)
    settings = init_app(config_path, options=options, settings=settings)
    mh = (settings or {}).get('mh')
    mailer = init_smtp_mailer(settings) if (not mh) else None
    plugin_loader = settings['plugin_loader']
    send_all_queued_messages(queue_dir, mailer, plugins=registry, mh=mh)
    plugin_loader.terminate_all_activated_plugins()

