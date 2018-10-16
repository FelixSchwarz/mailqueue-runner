# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os
import shutil

from pythonic_testcase import *

from schwarz.mailqueue import create_maildir_directories, DebugMailer, MaildirQueueRunner
from schwarz.mailqueue.lib.fake_fs_utils import TempFS
from schwarz.mailqueue.testutils import build_queued_msg, inject_message


class MaildirQueueRunnerTest(PythonicTestCase):
    def setUp(self):
        super(MaildirQueueRunnerTest, self).setUp()
        self.tempfs = TempFS.set_up(test=self)
        self.path_maildir = os.path.join(self.tempfs.root, 'mailqueue')
        create_maildir_directories(self.path_maildir)

    def test_can_send_message(self):
        mailer = DebugMailer()
        msg_bytes = b'Header: somevalue\n\nMsgBody\n'
        msg_fp = build_queued_msg(
            return_path=b'foo@site.example',
            envelope_to=b'bar@site.example',
            msg_bytes=msg_bytes,
        )
        msg_path = inject_message(self.path_maildir, msg_fp)
        assert_true(os.path.exists(msg_path))

        qr = MaildirQueueRunner(mailer)
        was_sent = qr.send_message(msg_path)
        assert_true(was_sent)

        assert_length(1, mailer.sent_mails)
        fromaddr, toaddrs, sent_msg = mailer.sent_mails[0]
        assert_equals('foo@site.example', fromaddr)
        assert_equals(('bar@site.example',), toaddrs)
        assert_equals(msg_bytes, sent_msg.read())
        assert_false(os.path.exists(msg_path))
        # ensure there are not left-overs/tmp files
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_sending_failure(self):
        mailer = DebugMailer(simulate_failed_sending=True)
        msg_path = inject_message(self.path_maildir, build_queued_msg())
        assert_true(os.path.exists(msg_path))

        qr = MaildirQueueRunner(mailer)
        was_sent = qr.send_message(msg_path)

        assert_false(was_sent)
        assert_true(os.path.exists(msg_path))
        # no left-overs (e.g. in "tmp" folder) other than the initial message file
        assert_length(1, self.list_all_files(self.path_maildir))

    def test_can_handle_non_existent_file_in_send(self):
        mailer = DebugMailer()
        invalid_path = os.path.join(self.path_maildir, 'new', 'invalid')
        qr = MaildirQueueRunner(mailer)
        was_sent = qr.send_message(invalid_path)

        assert_none(was_sent)
        assert_length(0, mailer.sent_mails)

    def test_can_handle_vanished_file_after_successful_send(self):
        msg_path = inject_message(self.path_maildir, build_queued_msg())
        path_in_progress = msg_path.replace('new', 'cur')
        def delete_on_send(*args):
            os.unlink(path_in_progress)
            return True
        mailer = DebugMailer(send_callback=delete_on_send)
        qr = MaildirQueueRunner(mailer)
        was_sent = qr.send_message(msg_path)

        assert_true(was_sent)
        assert_length(1, mailer.sent_mails)
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_vanished_file_after_failed_send(self):
        msg_path = inject_message(self.path_maildir, build_queued_msg())
        path_in_progress = msg_path.replace('new', 'cur')
        def delete_on_send(*args):
            os.unlink(path_in_progress)
            return False
        mailer = DebugMailer(send_callback=delete_on_send)
        qr = MaildirQueueRunner(mailer)
        was_sent = qr.send_message(msg_path)

        assert_false(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_duplicate_file_in_cur_before_send(self):
        msg_path = inject_message(self.path_maildir, build_queued_msg())
        path_in_progress = msg_path.replace('new', 'cur')
        # this can happen on Unix/Posix because Python does not provide an
        # atomic "move without overwrite". Linux provides the "renameat2"
        # system call (with RENAME_NOREPLACE flag) but Python does not expose
        # that API.
        shutil.copy(msg_path, path_in_progress)
        mailer = DebugMailer()
        qr = MaildirQueueRunner(mailer)
        was_sent = qr.send_message(msg_path)

        assert_none(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(2, self.list_all_files(self.path_maildir))

    def test_can_handle_duplicate_file_in_new_after_failed_send(self):
        msg_path = inject_message(self.path_maildir, build_queued_msg())
        path_in_progress = msg_path.replace('new', 'cur')
        # again: can happen because Python provides not atomic "move without
        # overwrite" on Linux (see also "renameat2" system call)
        def duplicate_on_failed_send(*args):
            shutil.copy(path_in_progress, msg_path)
            return False
        mailer = DebugMailer(send_callback=duplicate_on_failed_send)
        qr = MaildirQueueRunner(mailer)
        was_sent = qr.send_message(msg_path)

        assert_false(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(2, self.list_all_files(self.path_maildir))

    # --- internal helpers ----------------------------------------------------
    def list_all_files(self, basedir):
        files = []
        for root_dir, dirnames, filenames in os.walk(basedir):
            for filename in filenames:
                path = os.path.join(root_dir, filename)
                files.append(path)
        return files
