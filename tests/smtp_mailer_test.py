# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from pymta.api import IMTAPolicy
from pythonic_testcase import *

from schwarz.mailqueue import SMTPMailer
from schwarz.mailqueue.compat import IS_PYTHON3
from schwarz.mailqueue.testutils import FakeSMTP



class SMTPMailerTest(PythonicTestCase):
    def test_can_send_message_via_smtpmailer(self):
        fake_server = FakeSMTP()
        mailer = SMTPMailer(client=fake_server)
        fromaddr = 'foo@site.example'
        message = b'Header: value\n\nbody\n'
        toaddrs = ('bar@site.example', 'baz@site.example',)
        msg_was_sent = mailer.send(fromaddr, toaddrs, message)
        assert_true(msg_was_sent)

        received_queue = fake_server.received_messages
        assert_equals(1, received_queue.qsize())
        received_message = received_queue.get(block=False)
        assert_equals(fromaddr, received_message.smtp_from)
        assert_equals(toaddrs, tuple(received_message.smtp_to))
        assert_none(received_message.username)
        # pymta converts this to a string automatically
        expected_message = message.decode('ASCII')
        # in Python 2 the received message lacks the final '\n' (unknown reason)
        if not IS_PYTHON3:
            expected_message = expected_message.rstrip('\n')
        assert_equals(expected_message, received_message.msg_data)

    def test_can_handle_smtp_exception_after_from(self):
        reject_from = self._build_policy(accept_from=False)
        fake_server = FakeSMTP(policy=reject_from)
        mailer = SMTPMailer(client=fake_server)
        message = b'Header: value\n\nbody\n'
        msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

        assert_false(msg_was_sent)
        assert_equals(0, fake_server.received_messages.qsize())

    # --- internal helpers ----------------------------------------------------
    def _build_policy(self, **method_results):
        class TempPolicy(IMTAPolicy):
            pass

        for method_name, method_result in method_results.items():
            method = lambda policy, *args, **kwargs: method_result
            setattr(TempPolicy, method_name, method)
        return TempPolicy()

