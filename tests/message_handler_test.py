# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os
import shutil
try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock
import uuid

import pytest
from schwarz.log_utils import l_
from schwarz.puzzle_plugins import connect_signals, SignalRegistry
from testfixtures import LogCapture

from schwarz.mailqueue import (create_maildir_directories, lock_file,
    DebugMailer, MessageHandler)
from schwarz.mailqueue.compat import IS_WINDOWS
from schwarz.mailqueue.maildir_utils import find_messages
from schwarz.mailqueue.message_utils import parse_message_envelope
from schwarz.mailqueue.plugins import MQAction, MQSignal
from schwarz.mailqueue.queue_runner import MaildirBackedMsg, MaildirBackend
from schwarz.mailqueue.testutils import (assert_did_log_message, info_logger,
    inject_example_message, message as example_message)


@pytest.fixture
def path_maildir(tmpdir):
    path_maildir = os.path.join(tmpdir, 'mailqueue')
    create_maildir_directories(path_maildir)
    return path_maildir


@pytest.mark.parametrize('with_msg_id', [True, False])
def test_can_send_message(path_maildir, with_msg_id):
    mailer = DebugMailer()
    msg_header = b'X-Header: somevalue\n'
    if with_msg_id:
        msg_id = '%s@host.example' % uuid.uuid4()
        msg_header += b'Message-ID: <%s>\n' % msg_id.encode('ascii')
    msg_body = b'MsgBody\n'
    msg_bytes = msg_header + b'\n' + msg_body
    msg = inject_example_message(path_maildir,
        sender     = b'foo@site.example',
        recipient  = b'bar@site.example',
        msg_bytes  = msg_bytes,
    )
    assert os.path.exists(msg.path)

    with LogCapture() as lc:
        mh = MessageHandler([mailer], info_logger(lc))
        was_sent = mh.send_message(msg)
    assert bool(was_sent)
    expected_log_msg = '%s => %s' % ('foo@site.example', 'bar@site.example')
    if with_msg_id:
        expected_log_msg += ' <%s>' % msg_id
    assert_did_log_message(lc, expected_msg=expected_log_msg)

    assert len(mailer.sent_mails) == 1
    sent_msg, = mailer.sent_mails
    assert sent_msg.from_addr == 'foo@site.example'
    assert sent_msg.to_addrs == ('bar@site.example',)
    assert sent_msg.msg_fp.read() == msg_nl(msg_bytes)
    assert not os.path.exists(msg.path)
    # ensure there are no left-overs/tmp files
    assert len(list_all_files(path_maildir)) == 0

def test_can_handle_sending_failure(path_maildir):
    mailer = DebugMailer(simulate_failed_sending=True)
    msg = inject_example_message(path_maildir)
    assert os.path.exists(msg.path)

    was_sent = MessageHandler([mailer]).send_message(msg)
    assert not was_sent
    assert os.path.exists(msg.path)
    # no left-overs (e.g. in "tmp" folder) other than the initial message file
    assert len(list_all_files(path_maildir)) == 1

def test_can_handle_non_existent_file_in_send(path_maildir):
    mailer = DebugMailer()
    invalid_path = os.path.join(path_maildir, 'new', 'invalid')
    msg_with_invalid_path = MaildirBackedMsg(invalid_path)

    was_sent = MessageHandler([mailer]).send_message(msg_with_invalid_path)
    assert was_sent is None
    assert len(mailer.sent_mails) == 0

def test_can_handle_vanished_file_after_successful_send(path_maildir):
    if IS_WINDOWS:
        pytest.skip('unable to unlink open file on Windows')
    msg = inject_example_message(path_maildir)
    path_in_progress = msg.path.replace('new', 'cur')
    def delete_on_send(*args):
        os.unlink(path_in_progress)
        return True
    mailer = DebugMailer(send_callback=delete_on_send)

    was_sent = MessageHandler([mailer]).send_message(msg)
    assert was_sent
    assert len(mailer.sent_mails) == 1
    assert len(list_all_files(path_maildir)) == 0

def test_can_handle_vanished_file_after_failed_send(path_maildir):
    if IS_WINDOWS:
        pytest.skip('unable to unlink open file on Windows')
    msg = inject_example_message(path_maildir)
    path_in_progress = msg.path.replace('new', 'cur')
    def delete_on_send(*args):
        os.unlink(path_in_progress)
        return False
    mailer = DebugMailer(send_callback=delete_on_send)

    was_sent = MessageHandler([mailer]).send_message(msg)
    assert not was_sent
    assert len(mailer.sent_mails) == 0
    assert len(list_all_files(path_maildir)) == 0

def test_can_handle_duplicate_file_in_cur_before_send(path_maildir):
    msg = inject_example_message(path_maildir)
    path_in_progress = msg.path.replace('new', 'cur')
    # this can happen on Unix/Posix because Python does not provide an
    # atomic "move without overwrite". Linux provides the "renameat2"
    # system call (with RENAME_NOREPLACE flag) but Python does not expose
    # that API.
    shutil.copy(msg.path, path_in_progress)
    mailer = DebugMailer()

    was_sent = MessageHandler([mailer]).send_message(msg)
    assert was_sent is None
    assert len(mailer.sent_mails) == 0
    assert len(list_all_files(path_maildir)) == 2

def test_can_handle_duplicate_file_in_new_after_failed_send(path_maildir):
    msg = inject_example_message(path_maildir)
    path_in_progress = msg.path.replace('new', 'cur')
    # again: can happen because Python provides not atomic "move without
    # overwrite" on Linux (see also "renameat2" system call)
    def duplicate_on_failed_send(*args):
        shutil.copy(path_in_progress, msg.path)
        return False
    mailer = DebugMailer(send_callback=duplicate_on_failed_send)

    was_sent = MessageHandler([mailer]).send_message(msg)
    assert not was_sent
    assert len(mailer.sent_mails) == 0
    assert len(list_all_files(path_maildir)) == 2

def test_tries_to_lock_message_while_sending(path_maildir):
    mailer = DebugMailer()
    msg = inject_example_message(path_maildir)
    locked_msg = lock_file(msg.path, timeout=0.1)
    mh = MessageHandler([mailer])

    was_sent = mh.send_message(msg)
    assert was_sent is None
    assert len(msg_files(path_maildir, folder='new')) == 1
    assert not mailer.sent_mails

    locked_msg.close()
    was_sent = mh.send_message(msg)
    assert bool(was_sent)
    assert len(msg_files(path_maildir, folder='new')) == 0
    assert len(mailer.sent_mails) == 1

def test_can_enqueue_message_after_failed_sending(path_maildir):
    mailer = DebugMailer(simulate_failed_sending=True)
    maildir_fallback = MaildirBackend(path_maildir)
    msg = example_message()

    mh = MessageHandler([mailer, maildir_fallback])
    was_sent = mh.send_message(msg, sender='foo@site.example', recipient='bar@site.example')
    assert bool(was_sent)
    assert not mailer.sent_mails
    msg_path, = msg_files(path_maildir, folder='new')
    with open(msg_path, 'rb') as msg_fp:
        stored_msg = parse_message_envelope(msg_fp)
    assert stored_msg.from_addr == 'foo@site.example'
    assert stored_msg.to_addrs == ('bar@site.example',)

def test_can_enqueue_message_with_multiple_recipients_after_failed_sending(path_maildir):
    mailer = DebugMailer(simulate_failed_sending=True)
    mh = MessageHandler([mailer, MaildirBackend(path_maildir)])
    msg = example_message()
    recipients = ('r1@foo.example', 'r2@bar.example')

    mh.send_message(msg, sender='foo@site.example', recipients=recipients)
    msg_path, = msg_files(path_maildir, folder='new')
    with open(msg_path, 'rb') as msg_fp:
        stored_msg = parse_message_envelope(msg_fp)
    assert stored_msg.to_addrs == recipients

@pytest.mark.parametrize('delivery_successful', [True, False])
def test_can_notify_plugin_after_delivery(path_maildir, delivery_successful):
    if delivery_successful:
        signal = MQSignal.delivery_successful
        mailer = DebugMailer()
    else:
        signal = MQSignal.delivery_failed
        mailer = DebugMailer(simulate_failed_sending=True)
    registry = SignalRegistry()
    plugin = MagicMock(return_value=None, spec={})
    connect_signals({signal: plugin}, registry.namespace)

    mh = MessageHandler([mailer], plugins=registry)
    mh.send_message(example_message(), sender='foo@site.example', recipient='bar@site.example')

    plugin.assert_called_once()
    # would be able to simplify this with Python 3 only:
    # call_kwargs = plugin.call_args.kwargs
    call_kwargs = plugin.call_args[-1]
    send_result = call_kwargs['send_result']
    if delivery_successful:
        assert len(mailer.sent_mails) == 1
        assert bool(send_result)
    else:
        assert len(mailer.sent_mails) == 0
        assert not send_result
    assert not send_result.queued
    assert send_result.transport == 'debug'

def test_plugin_can_discard_message_after_failed_delivery(path_maildir):
    mailer = DebugMailer(simulate_failed_sending=True)
    sender = 'foo@site.example'
    recipient = 'bar@site.example'

    def discard_message(event_sender, msg, send_result):
        assert not send_result
        assert send_result.discarded is None
        assert msg.from_addr == sender
        assert set(msg.to_addrs) == {recipient}
        return MQAction.DISCARD

    registry = SignalRegistry()
    connect_signals({MQSignal.delivery_failed: discard_message}, registry.namespace)
    msg = example_message()
    mh = MessageHandler([mailer], plugins=registry)
    send_result = mh.send_message(msg, sender=sender, recipient=recipient)

    assert not send_result
    assert not send_result.queued
    assert send_result.discarded

def test_plugin_can_access_number_of_failed_deliveries(path_maildir):
    registry = SignalRegistry()
    def discard_after_two_attempts(sender, msg, send_result):
        return MQAction.DISCARD if (msg.retries > 1) else None
    connect_signals({MQSignal.delivery_failed: discard_after_two_attempts}, registry.namespace)

    msg = inject_example_message(path_maildir)
    mailer = DebugMailer(simulate_failed_sending=True)
    mh = MessageHandler([mailer], plugins=registry)

    mh.send_message(msg)
    assert len(tuple(find_messages(path_maildir, log=l_(None)))) == 1

    send_result = mh.send_message(msg)
    assert not send_result
    assert len(mailer.sent_mails) == 0
    assert len(tuple(find_messages(path_maildir, log=l_(None)))) == 0
    assert send_result.discarded


# --- internal helpers ----------------------------------------------------
def list_all_files(basedir):
    files = []
    for root_dir, dirnames, filenames in os.walk(basedir):
        for filename in filenames:
            path = os.path.join(root_dir, filename)
            files.append(path)
    return files

def msg_files(path_maildir, folder='new'):
    path = os.path.join(path_maildir, folder)
    files = []
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        files.append(file_path)
    return files


def msg_nl(msg_bytes):
    return msg_bytes if (not IS_WINDOWS) else msg_bytes.replace(b'\n', b'\r\n')

