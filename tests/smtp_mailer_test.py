# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from ddt import ddt as DataDrivenTestCase, data as ddt_data
from pymta.api import IMTAPolicy
from pymta.test_util import DummyAuthenticator
from pythonic_testcase import *

from schwarz.mailqueue import SMTPMailer
from schwarz.mailqueue.compat import IS_PYTHON3
from schwarz.mailqueue.testutils import (fake_smtp_client, stub_socket_creation,
    SocketMock)



@DataDrivenTestCase
class SMTPMailerTest(PythonicTestCase):
    def test_can_send_message_via_smtpmailer(self):
        fake_client = fake_smtp_client()
        mailer = SMTPMailer(client=fake_client)
        fromaddr = 'foo@site.example'
        message = b'Header: value\n\nbody\n'
        toaddrs = ('bar@site.example', 'baz@site.example',)
        msg_was_sent = mailer.send(fromaddr, toaddrs, message)
        assert_true(msg_was_sent)

        received_queue = fake_client.server.received_messages
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

    def test_can_handle_connection_error(self):
        overrides = self._build_overrides(connect=OSError('error on connect'))
        fake_client = fake_smtp_client(overrides=overrides)
        mailer = SMTPMailer(client=fake_client)
        message = b'Header: value\n\nbody\n'
        # We want to check that "SMTPMailer" is able to handle the "OSError"
        # which is raised in ".connect()" (see "overrides" above).
        # As we inject our "fake_client" directly into the SMTPMailer (this
        # makes our testing code easier) "fake_smtp_client()" ensures that the
        # actual call to ".connect()" is delayed until now.
        # That means we need to stub out the "socket.create_connection()" call
        # again.
        with stub_socket_creation(fake_client.server):
            msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

        assert_false(msg_was_sent)
        assert_equals(0, fake_client.server.received_messages.qsize())

    def test_can_handle_smtp_exception_after_from(self):
        reject_from = self._build_policy(accept_from=False)
        fake_client = fake_smtp_client(policy=reject_from)
        mailer = SMTPMailer(client=fake_client)
        message = b'Header: value\n\nbody\n'
        msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

        assert_false(msg_was_sent)
        assert_equals(0, fake_client.server.received_messages.qsize())

    @ddt_data('PLAIN', 'LOGIN')
    def test_can_use_smtp_auth(self, auth_type):
        class AuthPolicy(IMTAPolicy):
            def auth_methods(self, peer):
                return (auth_type,)
        socket_mock = SocketMock(policy=AuthPolicy(), authenticator=DummyAuthenticator())

        fake_client = fake_smtp_client(socket_mock=socket_mock)
        mailer = SMTPMailer(client=fake_client, username='foo', password='foo')
        message = b'Header: value\n\nbody\n'
        msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

        assert_true(msg_was_sent)
        received_queue = fake_client.server.received_messages
        assert_equals(1, received_queue.qsize())

    # --- internal helpers ----------------------------------------------------
    def _build_policy(self, **method_results):
        class TempPolicy(IMTAPolicy):
            pass

        for method_name, method_result in method_results.items():
            method = lambda policy, *args, **kwargs: method_result
            setattr(TempPolicy, method_name, method)
        return TempPolicy()

    def _build_overrides(self, **overrides):
        _overrides = {}
        for method_name, exception in overrides.items():
            def raise_exc():
                raise exception
            _overrides[method_name] = raise_exc
        return _overrides

