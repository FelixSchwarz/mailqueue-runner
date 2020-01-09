# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os
import shutil
import uuid

from ddt import ddt as DataDrivenTestCase, data as ddt_data
from pythonic_testcase import *
from schwarz.fakefs_helpers import TempFS
from testfixtures import LogCapture

from schwarz.mailqueue import (create_maildir_directories, enqueue_message,
     testutils, DebugMailer, MessageHandler)
from schwarz.mailqueue.testutils import assert_did_log_message, info_logger


@DataDrivenTestCase
class MessageHandlerTest(PythonicTestCase):
    def setUp(self):
        self.tempfs = TempFS.set_up(test=self)
        self.path_maildir = os.path.join(self.tempfs.root, 'mailqueue')
        create_maildir_directories(self.path_maildir)

    @ddt_data(True, False)
    def test_can_send_message(self, with_msg_id):
        mailer = DebugMailer()
        msg_header = b'X-Header: somevalue\n'
        if with_msg_id:
            msg_id = '%s@host.example' % uuid.uuid4()
            msg_header += b'Message-ID: <%s>\n' % msg_id.encode('ascii')
        msg_body = b'MsgBody\n'
        msg_bytes = msg_header + b'\n' + msg_body
        msg_path = enqueue_message(
            msg_bytes,
            self.path_maildir,
            sender=b'foo@site.example',
            recipient=b'bar@site.example'
        )
        assert_true(os.path.exists(msg_path))

        with LogCapture() as lc:
            mh = MessageHandler(mailer, info_logger(lc))
            was_sent = mh.send_message(msg_path)
        assert_true(was_sent)
        expected_log_msg = '%s => %s' % ('foo@site.example', 'bar@site.example')
        if with_msg_id:
            expected_log_msg += ' <%s>' % msg_id
        assert_did_log_message(lc, expected_msg=expected_log_msg)

        assert_length(1, mailer.sent_mails)
        fromaddr, toaddrs, sent_msg = mailer.sent_mails[0]
        assert_equals('foo@site.example', fromaddr)
        assert_equals(('bar@site.example',), toaddrs)
        assert_equals(msg_bytes, sent_msg)
        assert_false(os.path.exists(msg_path))
        # ensure there are not left-overs/tmp files
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_sending_failure(self):
        mailer = DebugMailer(simulate_failed_sending=True)
        msg_path = inject_example_message(self.path_maildir)
        assert_true(os.path.exists(msg_path))

        mh = MessageHandler(mailer)
        was_sent = mh.send_message(msg_path)

        assert_false(was_sent)
        assert_true(os.path.exists(msg_path))
        # no left-overs (e.g. in "tmp" folder) other than the initial message file
        assert_length(1, self.list_all_files(self.path_maildir))

    def test_can_handle_non_existent_file_in_send(self):
        mailer = DebugMailer()
        invalid_path = os.path.join(self.path_maildir, 'new', 'invalid')
        mh = MessageHandler(mailer)
        was_sent = mh.send_message(invalid_path)

        assert_none(was_sent)
        assert_length(0, mailer.sent_mails)

    def test_can_handle_vanished_file_after_successful_send(self):
        msg_path = inject_example_message(self.path_maildir)
        path_in_progress = msg_path.replace('new', 'cur')
        def delete_on_send(*args):
            os.unlink(path_in_progress)
            return True
        mailer = DebugMailer(send_callback=delete_on_send)
        mh = MessageHandler(mailer)
        was_sent = mh.send_message(msg_path)

        assert_true(was_sent)
        assert_length(1, mailer.sent_mails)
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_vanished_file_after_failed_send(self):
        msg_path = inject_example_message(self.path_maildir)
        path_in_progress = msg_path.replace('new', 'cur')
        def delete_on_send(*args):
            os.unlink(path_in_progress)
            return False
        mailer = DebugMailer(send_callback=delete_on_send)
        mh = MessageHandler(mailer)
        was_sent = mh.send_message(msg_path)

        assert_false(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_duplicate_file_in_cur_before_send(self):
        msg_path = inject_example_message(self.path_maildir)
        path_in_progress = msg_path.replace('new', 'cur')
        # this can happen on Unix/Posix because Python does not provide an
        # atomic "move without overwrite". Linux provides the "renameat2"
        # system call (with RENAME_NOREPLACE flag) but Python does not expose
        # that API.
        shutil.copy(msg_path, path_in_progress)
        mailer = DebugMailer()
        mh = MessageHandler(mailer)
        was_sent = mh.send_message(msg_path)

        assert_none(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(2, self.list_all_files(self.path_maildir))

    def test_can_handle_duplicate_file_in_new_after_failed_send(self):
        msg_path = inject_example_message(self.path_maildir)
        path_in_progress = msg_path.replace('new', 'cur')
        # again: can happen because Python provides not atomic "move without
        # overwrite" on Linux (see also "renameat2" system call)
        def duplicate_on_failed_send(*args):
            shutil.copy(path_in_progress, msg_path)
            return False
        mailer = DebugMailer(send_callback=duplicate_on_failed_send)
        mh = MessageHandler(mailer)
        was_sent = mh.send_message(msg_path)

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


def inject_example_message(queue_path, sender=b'foo@site.example', recipient=b'bar@site.example', msg_bytes=None):
    if msg_bytes is None:
        msg_bytes = testutils.message()
    return enqueue_message(msg_bytes, queue_path, sender, recipient)
