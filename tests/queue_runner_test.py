# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime as DateTime, timedelta as TimeDelta
import os

from boltons.timeutils import UTC
import pytest
from pythonic_testcase import *
try:
    from time_machine import travel as freeze_time
except ImportError:
    from freezegun import freeze_time
from testfixtures import LogCapture

from schwarz.mailqueue import (create_maildir_directories, lock_file,
    send_all_queued_messages, DebugMailer)
from schwarz.mailqueue.queue_runner import MaildirBackedMsg
from schwarz.mailqueue.testutils import inject_example_message


@pytest.fixture
def path_maildir(tmpdir):
    _path_maildir = os.path.join(tmpdir, 'mailqueue')
    create_maildir_directories(_path_maildir)
    return _path_maildir


def test_can_move_stale_messages_back_to_new(path_maildir):
    mailer = DebugMailer()
    inject_example_message(path_maildir, target_folder='cur')

    send_all_queued_messages(path_maildir, mailer)
    assert_is_empty(mailer.sent_mails)
    assert_is_empty(msg_files(path_maildir, folder='new'))
    assert_length(1, msg_files(path_maildir, folder='cur'))

    dt_stale = DateTime.now() + TimeDelta(hours=1)
    # LogCapture: no logged warning about stale message on the command line
    with LogCapture():
        with freeze_time(dt_stale):
            send_all_queued_messages(path_maildir, mailer)
    assert_is_empty(msg_files(path_maildir, folder='new'))
    assert_is_empty(msg_files(path_maildir, folder='cur'))
    assert_length(1, mailer.sent_mails)

def test_can_handle_concurrent_sends(path_maildir):
    mailer = DebugMailer()
    msg = inject_example_message(path_maildir)
    locked_msg = lock_file(msg.path, timeout=0.1)

    send_all_queued_messages(path_maildir, mailer)
    assert_length(1, msg_files(path_maildir, folder='new'))
    assert_is_empty(mailer.sent_mails)

    locked_msg.close()
    send_all_queued_messages(path_maildir, mailer)
    assert_is_empty(msg_files(path_maildir, folder='new'))
    assert_length(1, mailer.sent_mails)

def test_can_send_queued_message_to_multiple_recipients(path_maildir):
    mailer = DebugMailer()
    recipients = (b'r1@foo.example', b'r2@bar.example')
    inject_example_message(path_maildir, recipients=recipients)

    send_all_queued_messages(path_maildir, mailer)
    assert_is_empty(msg_files(path_maildir, folder='new'))
    sent_msg, = mailer.sent_mails
    _as_str = lambda values: tuple([v.decode('ascii') for v in values])
    assert_equals(_as_str(recipients), sent_msg.to_addrs)

def test_can_handle_failures_and_update_metadata(path_maildir):
    mailer = DebugMailer(simulate_failed_sending=True)
    queue_date = DateTime(2020, 2, 4, hour=14, minute=32, tzinfo=UTC)
    inject_example_message(path_maildir, queue_date=queue_date)

    send_all_queued_messages(path_maildir, mailer)
    assert_is_empty(mailer.sent_mails)

    msg_file, = msg_files(path_maildir, folder='new')
    msg = MaildirBackedMsg(msg_file)
    assert_equals(queue_date, msg.queue_date)
    assert_equals(1, msg.retries)
    assert_not_none(msg.last_delivery_attempt)
    assert_almost_now(msg.last_delivery_attempt)

def msg_files(path_maildir, folder='new'):
    path = os.path.join(path_maildir, folder)
    files = []
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        files.append(file_path)
    return files

