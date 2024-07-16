# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

import pytest

from schwarz.mailqueue import enqueue_message, DebugMailer, MessageHandler
from schwarz.mailqueue.testutils import message as example_message


@pytest.fixture
def path_maildir(tmpdir):
    return os.path.join(tmpdir, 'mailqueue')


def test_can_create_missing_maildir_folders_before_enqueueing_message(path_maildir):
    # important for regression test: mailqueue parent folder exists but
    # "new"/"cur"/"tmp" are missing.
    for sub_dir in ('new', 'cur', 'tmp'):
        sub_path = os.path.join(path_maildir, sub_dir)
        assert not os.path.exists(sub_path)
    msg = example_message()

    enqueue_message(msg, path_maildir, sender='foo@site.example', recipients=('bar@site.example',))
    assert len(_msg_files(path_maildir, folder='new')) == 1


def test_can_store_message_on_disk_before_sending(path_maildir):
    msg = example_message()
    md_msg = enqueue_message(msg, path_maildir,
        sender      = 'foo@site.example',
        recipients  = ('bar@site.example',),
        in_progress = True,
        return_msg  = True,
    )
    assert len(_msg_files(path_maildir, folder='new')) == 0
    assert len(_msg_files(path_maildir, folder='cur')) == 1

    mailer = DebugMailer()
    mh = MessageHandler([mailer])
    send_result = mh.send_message(md_msg)
    assert bool(send_result)

    assert len(mailer.sent_mails) == 1
    assert len(_msg_files(path_maildir, folder='new')) == 0
    assert len(_msg_files(path_maildir, folder='cur')) == 0

# --- internal helpers ----------------------------------------------------
def _msg_files(path_maildir, folder='new'):
    path = os.path.join(path_maildir, folder)
    files = []
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        files.append(file_path)
    return files

