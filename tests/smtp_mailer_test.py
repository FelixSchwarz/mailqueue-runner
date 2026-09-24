# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import socket

import pytest
from pymta.api import IMTAPolicy
from pymta.test_util import DummyAuthenticator
from schwarz.log_utils.testutils import build_collecting_logger

from schwarz.mailqueue import SMTPMailer
from schwarz.mailqueue.smtpclient import SMTPRecipientRefused
from schwarz.mailqueue.testutils import SocketMock, fake_smtp_client, stub_socket_creation


def test_can_send_message_via_smtpmailer():
    fake_client = fake_smtp_client()
    mailer = SMTPMailer(client=fake_client)
    fromaddr = 'foo@site.example'
    message = b'Header: value\n\nbody\n'
    toaddrs = ('bar@site.example', 'baz@site.example',)
    msg_was_sent = mailer.send(fromaddr, toaddrs, message)
    assert msg_was_sent

    received_queue = fake_client.server.received_messages
    assert received_queue.qsize() == 1
    received_message = received_queue.get(block=False)
    assert received_message.smtp_from == fromaddr
    assert tuple(received_message.smtp_to) == toaddrs
    assert received_message.username is None
    # The message is sent with CRLF line endings. pymta converts line endings
    # to "\n" and the final line break is part of the "end of data" marker.
    expected_message = 'Header: value\n\nbody'
    assert received_message.msg_data == expected_message

def test_can_handle_connection_error():
    exc = socket.error(101, 'Network is unreachable')
    overrides = _build_overrides(connect=exc)
    fake_client = fake_smtp_client(overrides=overrides)
    logger, logs = build_collecting_logger()
    mailer = SMTPMailer(client=fake_client, smtp_log=logger)
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

    assert not msg_was_sent
    assert fake_client.server.received_messages.qsize() == 0
    assert len(logs.buffer) == 1
    expected_msg = '%s (%s)' % (str(exc), exc.__class__.__name__)
    lr, = logs.buffer
    assert lr.msg == expected_msg

def test_can_handle_smtp_exception_after_from():
    reject_from = _build_policy(accept_from=False)
    fake_client = fake_smtp_client(policy=reject_from)
    mailer = SMTPMailer(client=fake_client)
    message = b'Header: value\n\nbody\n'
    msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

    assert not msg_was_sent
    assert fake_client.server.received_messages.qsize() == 0


def test_does_not_send_message_if_any_recipient_was_refused():
    class RejectRecipientPolicy(IMTAPolicy):
        def accept_rcpt_to(self, new_recipient, message):
            return (new_recipient != 'baz@site.example')
    fake_client = fake_smtp_client(policy=RejectRecipientPolicy())
    logger, logs = build_collecting_logger()
    mailer = SMTPMailer(client=fake_client, smtp_log=logger)
    message = b'Header: value\n\nbody\n'
    toaddrs = ('bar@site.example', 'baz@site.example', 'qux@site.example')
    msg_was_sent = mailer.send('foo@site.example', toaddrs, message)

    # Python's smtplib would deliver the message to all accepted recipients
    # and only report the refused ones. mailqueue-runner must not do that:
    # Otherwise we could only retry delivery to the refused recipients by
    # sending the message again to all recipients.
    assert not msg_was_sent
    assert fake_client.server.received_messages.qsize() == 0

def test_client_raises_recipient_refused_if_any_recipient_was_refused():
    class RejectRecipientPolicy(IMTAPolicy):
        def accept_rcpt_to(self, new_recipient, message):
            return (new_recipient != 'baz@site.example')
    fake_client = fake_smtp_client(policy=RejectRecipientPolicy())
    message = b'Header: value\n\nbody\n'
    toaddrs = ('bar@site.example', 'baz@site.example')
    with pytest.raises(SMTPRecipientRefused) as exc_info:
        fake_client.sendmail('foo@site.example', toaddrs, message)

    exc = exc_info.value
    assert exc.recipient == 'baz@site.example'
    assert exc.smtp_code == 550
    assert fake_client.server.received_messages.qsize() == 0


@pytest.mark.parametrize('auth_type', ['PLAIN', 'LOGIN'])
def test_can_use_smtp_auth(auth_type):
    class AuthPolicy(IMTAPolicy):
        def auth_methods(self, peer):
            return (auth_type,)
    socket_mock = SocketMock(policy=AuthPolicy(), authenticator=DummyAuthenticator())

    fake_client = fake_smtp_client(socket_mock=socket_mock)
    mailer = SMTPMailer(client=fake_client, username='foo', password='foo')
    message = b'Header: value\n\nbody\n'
    msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

    assert msg_was_sent
    received_queue = fake_client.server.received_messages
    assert received_queue.qsize() == 1

# --- internal helpers ----------------------------------------------------
def _build_policy(**method_results):
    class TempPolicy(IMTAPolicy):
        pass

    for method_name, method_result in method_results.items():
        method = lambda policy, *args, **kwargs: method_result
        setattr(TempPolicy, method_name, method)
    return TempPolicy()

def _build_overrides(**overrides):
    _overrides = {}
    for method_name, exception in overrides.items():
        def raise_exc():
            raise exception
        _overrides[method_name] = raise_exc
    return _overrides
