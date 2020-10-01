# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime as DateTime, timedelta as TimeDelta
import os

from freezegun import freeze_time
from pythonic_testcase import *
from schwarz.fakefs_helpers import TempFS
from testfixtures import LogCapture

from schwarz.mailqueue import (create_maildir_directories, lock_file,
    send_all_queued_messages, DebugMailer)
from schwarz.mailqueue.testutils import inject_example_message


class QueueRunnerTest(PythonicTestCase):
    def setUp(self):
        self.tempfs = TempFS.set_up(test=self)
        self.path_maildir = os.path.join(self.tempfs.root, 'mailqueue')
        create_maildir_directories(self.path_maildir)

    def test_can_move_stale_messages_back_to_new(self):
        mailer = DebugMailer()
        inject_example_message(self.path_maildir, target_folder='cur')

        send_all_queued_messages(self.path_maildir, mailer)
        assert_is_empty(mailer.sent_mails)
        assert_is_empty(self.msg_files(folder='new'))
        assert_length(1, self.msg_files(folder='cur'))

        dt_stale = DateTime.now() + TimeDelta(hours=1)
        # LogCapture: no logged warning about stale message on the command line
        with LogCapture():
            with freeze_time(dt_stale):
                send_all_queued_messages(self.path_maildir, mailer)
        assert_is_empty(self.msg_files(folder='new'))
        assert_is_empty(self.msg_files(folder='cur'))
        assert_length(1, mailer.sent_mails)

    def test_can_handle_concurrent_sends(self):
        mailer = DebugMailer()
        msg = inject_example_message(self.path_maildir)
        locked_msg = lock_file(msg.path, timeout=0.1)

        send_all_queued_messages(self.path_maildir, mailer)
        assert_length(1, self.msg_files(folder='new'))
        assert_is_empty(mailer.sent_mails)

        locked_msg.close()
        send_all_queued_messages(self.path_maildir, mailer)
        assert_is_empty(self.msg_files(folder='new'))
        assert_length(1, mailer.sent_mails)

    def test_can_send_queued_message_to_multiple_recipients(self):
        mailer = DebugMailer()
        recipients = (b'r1@foo.example', b'r2@bar.example')
        inject_example_message(self.path_maildir, recipients=recipients)

        send_all_queued_messages(self.path_maildir, mailer)
        assert_is_empty(self.msg_files(folder='new'))
        sent_msg, = mailer.sent_mails
        _as_str = lambda values: tuple([v.decode('ascii') for v in values])
        assert_equals(_as_str(recipients), sent_msg.to_addrs)

    def msg_files(self, folder='new'):
        path = os.path.join(self.path_maildir, folder)
        files = []
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            files.append(file_path)
        return files

