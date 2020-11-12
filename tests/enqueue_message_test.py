# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

from pythonic_testcase import *
from schwarz.fakefs_helpers import TempFS

from schwarz.mailqueue import enqueue_message, DebugMailer, MessageHandler
from schwarz.mailqueue.testutils import message as example_message


class EnqueueMessageTest(PythonicTestCase):
    def setUp(self):
        self.tempfs = TempFS.set_up(test=self)
        self.path_maildir = os.path.join(self.tempfs.root, 'mailqueue')

    def test_can_create_missing_maildir_folders_before_enqueueing_message(self):
        # important for regression test: mailqueue parent folder exists but
        # "new"/"cur"/"tmp" are missing.
        for sub_dir in ('new', 'cur', 'tmp'):
            sub_path = os.path.join(self.path_maildir, sub_dir)
            assert_false(os.path.exists(sub_path))
        msg = example_message()

        enqueue_message(msg, self.path_maildir, sender='foo@site.example', recipients=('bar@site.example',))
        assert_length(1, self.msg_files(folder='new'))

    def test_can_store_message_on_disk_before_sending(self):
        msg = example_message()
        md_msg = enqueue_message(msg, self.path_maildir,
            sender      = 'foo@site.example',
            recipients  = ('bar@site.example',),
            in_progress = True,
            return_msg  = True,
        )
        assert_length(0, self.msg_files(folder='new'))
        assert_length(1, self.msg_files(folder='cur'))

        mailer = DebugMailer()
        mh = MessageHandler([mailer])
        send_result = mh.send_message(md_msg)
        assert_trueish(send_result)

        assert_length(1, mailer.sent_mails)
        assert_length(0, self.msg_files(folder='new'))
        assert_length(0, self.msg_files(folder='cur'))

    # --- internal helpers ----------------------------------------------------
    def msg_files(self, folder='new'):
        path = os.path.join(self.path_maildir, folder)
        files = []
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            files.append(file_path)
        return files

