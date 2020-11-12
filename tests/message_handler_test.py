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

from ddt import ddt as DataDrivenTestCase, data as ddt_data
from pythonic_testcase import *
from schwarz.fakefs_helpers import TempFS
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
        msg = inject_example_message(self.path_maildir,
            sender     = b'foo@site.example',
            recipient  = b'bar@site.example',
            msg_bytes  = msg_bytes,
        )
        assert_true(os.path.exists(msg.path))

        with LogCapture() as lc:
            mh = MessageHandler([mailer], info_logger(lc))
            was_sent = mh.send_message(msg)
        assert_trueish(was_sent)
        expected_log_msg = '%s => %s' % ('foo@site.example', 'bar@site.example')
        if with_msg_id:
            expected_log_msg += ' <%s>' % msg_id
        assert_did_log_message(lc, expected_msg=expected_log_msg)

        assert_length(1, mailer.sent_mails)
        sent_msg, = mailer.sent_mails
        assert_equals('foo@site.example', sent_msg.from_addr)
        assert_equals(('bar@site.example',), sent_msg.to_addrs)
        assert_equals(msg_nl(msg_bytes), sent_msg.msg_fp.read())
        assert_false(os.path.exists(msg.path))
        # ensure there are no left-overs/tmp files
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_sending_failure(self):
        mailer = DebugMailer(simulate_failed_sending=True)
        msg = inject_example_message(self.path_maildir)
        assert_true(os.path.exists(msg.path))

        was_sent = MessageHandler([mailer]).send_message(msg)
        assert_falseish(was_sent)
        assert_true(os.path.exists(msg.path))
        # no left-overs (e.g. in "tmp" folder) other than the initial message file
        assert_length(1, self.list_all_files(self.path_maildir))

    def test_can_handle_non_existent_file_in_send(self):
        mailer = DebugMailer()
        invalid_path = os.path.join(self.path_maildir, 'new', 'invalid')
        msg_with_invalid_path = MaildirBackedMsg(invalid_path)

        was_sent = MessageHandler([mailer]).send_message(msg_with_invalid_path)
        assert_none(was_sent)
        assert_length(0, mailer.sent_mails)

    def test_can_handle_vanished_file_after_successful_send(self):
        if IS_WINDOWS:
            self.skipTest('unable to unlink open file on Windows')
        msg = inject_example_message(self.path_maildir)
        path_in_progress = msg.path.replace('new', 'cur')
        def delete_on_send(*args):
            os.unlink(path_in_progress)
            return True
        mailer = DebugMailer(send_callback=delete_on_send)

        was_sent = MessageHandler([mailer]).send_message(msg)
        assert_true(was_sent)
        assert_length(1, mailer.sent_mails)
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_vanished_file_after_failed_send(self):
        if IS_WINDOWS:
            self.skipTest('unable to unlink open file on Windows')
        msg = inject_example_message(self.path_maildir)
        path_in_progress = msg.path.replace('new', 'cur')
        def delete_on_send(*args):
            os.unlink(path_in_progress)
            return False
        mailer = DebugMailer(send_callback=delete_on_send)

        was_sent = MessageHandler([mailer]).send_message(msg)
        assert_false(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(0, self.list_all_files(self.path_maildir))

    def test_can_handle_duplicate_file_in_cur_before_send(self):
        msg = inject_example_message(self.path_maildir)
        path_in_progress = msg.path.replace('new', 'cur')
        # this can happen on Unix/Posix because Python does not provide an
        # atomic "move without overwrite". Linux provides the "renameat2"
        # system call (with RENAME_NOREPLACE flag) but Python does not expose
        # that API.
        shutil.copy(msg.path, path_in_progress)
        mailer = DebugMailer()

        was_sent = MessageHandler([mailer]).send_message(msg)
        assert_none(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(2, self.list_all_files(self.path_maildir))

    def test_can_handle_duplicate_file_in_new_after_failed_send(self):
        msg = inject_example_message(self.path_maildir)
        path_in_progress = msg.path.replace('new', 'cur')
        # again: can happen because Python provides not atomic "move without
        # overwrite" on Linux (see also "renameat2" system call)
        def duplicate_on_failed_send(*args):
            shutil.copy(path_in_progress, msg.path)
            return False
        mailer = DebugMailer(send_callback=duplicate_on_failed_send)

        was_sent = MessageHandler([mailer]).send_message(msg)
        assert_false(was_sent)
        assert_length(0, mailer.sent_mails)
        assert_length(2, self.list_all_files(self.path_maildir))

    def test_tries_to_lock_message_while_sending(self):
        mailer = DebugMailer()
        msg = inject_example_message(self.path_maildir)
        locked_msg = lock_file(msg.path, timeout=0.1)
        mh = MessageHandler([mailer])

        was_sent = mh.send_message(msg)
        assert_none(was_sent)
        assert_length(1, self.msg_files(folder='new'))
        assert_is_empty(mailer.sent_mails)

        locked_msg.close()
        was_sent = mh.send_message(msg)
        assert_trueish(was_sent)
        assert_is_empty(self.msg_files(folder='new'))
        assert_length(1, mailer.sent_mails)

    def test_can_enqueue_message_after_failed_sending(self):
        mailer = DebugMailer(simulate_failed_sending=True)
        maildir_fallback = MaildirBackend(self.path_maildir)
        msg = example_message()

        mh = MessageHandler([mailer, maildir_fallback])
        was_sent = mh.send_message(msg, sender='foo@site.example', recipient='bar@site.example')
        assert_trueish(was_sent)
        assert_is_empty(mailer.sent_mails)
        msg_path, = self.msg_files(folder='new')
        with open(msg_path, 'rb') as msg_fp:
            stored_msg = parse_message_envelope(msg_fp)
        assert_equals('foo@site.example', stored_msg.from_addr)
        assert_equals(('bar@site.example',), stored_msg.to_addrs)

    def test_can_enqueue_message_with_multiple_recipients_after_failed_sending(self):
        mailer = DebugMailer(simulate_failed_sending=True)
        mh = MessageHandler([mailer, MaildirBackend(self.path_maildir)])
        msg = example_message()
        recipients = ('r1@foo.example', 'r2@bar.example')

        mh.send_message(msg, sender='foo@site.example', recipients=recipients)
        msg_path, = self.msg_files(folder='new')
        with open(msg_path, 'rb') as msg_fp:
            stored_msg = parse_message_envelope(msg_fp)
        assert_equals(recipients, stored_msg.to_addrs)

    @ddt_data(True, False)
    def test_can_notify_plugin_after_delivery(self, delivery_successful):
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
            assert_length(1, mailer.sent_mails)
            assert_trueish(send_result)
        else:
            assert_length(0, mailer.sent_mails)
            assert_falseish(send_result)
        assert_false(send_result.queued)
        assert_equals('debug', send_result.transport)

    def test_plugin_can_discard_message_after_failed_delivery(self):
        mailer = DebugMailer(simulate_failed_sending=True)
        sender = 'foo@site.example'
        recipient = 'bar@site.example'

        def discard_message(event_sender, msg, send_result):
            assert_falseish(send_result)
            assert_none(send_result.discarded)
            assert_equals(sender, msg.from_addr)
            assert_equals({recipient}, set(msg.to_addrs))
            return MQAction.DISCARD

        registry = SignalRegistry()
        connect_signals({MQSignal.delivery_failed: discard_message}, registry.namespace)
        msg = example_message()
        mh = MessageHandler([mailer], plugins=registry)
        send_result = mh.send_message(msg, sender=sender, recipient=recipient)

        assert_falseish(send_result)
        assert_false(send_result.queued)
        assert_true(send_result.discarded)

    def test_plugin_can_access_number_of_failed_deliveries(self):
        registry = SignalRegistry()
        def discard_after_two_attempts(sender, msg, send_result):
            return MQAction.DISCARD if (msg.retries > 1) else None
        connect_signals({MQSignal.delivery_failed: discard_after_two_attempts}, registry.namespace)

        msg = inject_example_message(self.path_maildir)
        mailer = DebugMailer(simulate_failed_sending=True)
        mh = MessageHandler([mailer], plugins=registry)

        mh.send_message(msg)
        assert_length(1, find_messages(self.path_maildir, log=l_(None)))

        send_result = mh.send_message(msg)
        assert_falseish(send_result)
        assert_length(0, mailer.sent_mails)
        assert_length(0, find_messages(self.path_maildir, log=l_(None)))
        assert_true(send_result.discarded)


    # --- internal helpers ----------------------------------------------------
    def list_all_files(self, basedir):
        files = []
        for root_dir, dirnames, filenames in os.walk(basedir):
            for filename in filenames:
                path = os.path.join(root_dir, filename)
                files.append(path)
        return files

    def msg_files(self, folder='new'):
        path = os.path.join(self.path_maildir, folder)
        files = []
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            files.append(file_path)
        return files


def msg_nl(msg_bytes):
    return msg_bytes if (not IS_WINDOWS) else msg_bytes.replace(b'\n', b'\r\n')

