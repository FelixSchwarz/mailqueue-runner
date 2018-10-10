# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

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

        qr = MaildirQueueRunner(mailer, self.path_maildir)
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

        qr = MaildirQueueRunner(mailer, self.path_maildir)
        was_sent = qr.send_message(msg_path)

        assert_false(was_sent)
        assert_true(os.path.exists(msg_path))
        # no left-overs (e.g. in "tmp" folder) other than the initial message file
        assert_length(1, self.list_all_files(self.path_maildir))

    # --- internal helpers ----------------------------------------------------
    def list_all_files(self, basedir):
        files = []
        for root_dir, dirnames, filenames in os.walk(basedir):
            for filename in filenames:
                path = os.path.join(root_dir, filename)
                files.append(path)
        return files
