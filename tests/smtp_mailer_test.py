# SPDX-License-Identifier: MIT

import logging
from unittest import mock

import pytest
from schwarz.log_utils.testutils import build_collecting_logger

from schwarz.mailqueue import SMTPMailer, TLSMode, init_smtp_mailer
from schwarz.mailqueue.smtpclient import SMTPRecipientRefused
from schwarz.mailqueue.testutils import (
    MessageCollector,
    SocketMock,
    accept_any_login,
    fake_smtp_client,
    stub_socket_creation,
)


def test_can_send_message_via_smtpmailer():
    fake_client = fake_smtp_client()
    mailer = SMTPMailer(client=fake_client)
    fromaddr = 'foo@site.example'
    message = b'Header: value\n\nbody\n'
    toaddrs = ('bar@site.example', 'baz@site.example',)
    msg_was_sent = mailer.send(fromaddr, toaddrs, message)
    assert msg_was_sent
    assert msg_was_sent.smtp_response.code == 250

    received_queue = fake_client.server.received_messages
    assert received_queue.qsize() == 1
    received_message = received_queue.get(block=False)
    assert received_message.smtp_from == fromaddr
    assert tuple(received_message.smtp_to) == toaddrs
    assert received_message.username is None
    # The message is sent with CRLF line endings.
    assert received_message.msg_bytes == b'Header: value\r\n\r\nbody\r\n'

def test_can_handle_connection_error():
    exc = OSError(101, 'Network is unreachable')
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
    assert msg_was_sent.error == str(exc)
    assert fake_client.server.received_messages.qsize() == 0
    assert len(logs.buffer) == 1
    expected_msg = '%s (%s)' % (str(exc), exc.__class__.__name__)
    lr, = logs.buffer
    assert lr.msg == expected_msg

def test_can_handle_smtp_exception_after_from():
    class RejectSenderHandler(MessageCollector):
        async def handle_MAIL(self, server, session, envelope, address, mail_options):
            return '550 sender rejected'
    fake_client = fake_smtp_client(handler=RejectSenderHandler())
    mailer = SMTPMailer(client=fake_client)
    message = b'Header: value\n\nbody\n'
    msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

    assert not msg_was_sent
    assert msg_was_sent.smtp_response.code == 550
    assert fake_client.server.received_messages.qsize() == 0


def test_does_not_send_message_if_any_recipient_was_refused():
    fake_client = fake_smtp_client(handler=RejectRecipientHandler('baz@site.example'))
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
    fake_client = fake_smtp_client(handler=RejectRecipientHandler('baz@site.example'))
    message = b'Header: value\n\nbody\n'
    toaddrs = ('bar@site.example', 'baz@site.example')
    with pytest.raises(SMTPRecipientRefused) as exc_info:
        fake_client.sendmail('foo@site.example', toaddrs, message)

    exc = exc_info.value
    assert exc.recipient == 'baz@site.example'
    assert exc.smtp_code == 550
    assert fake_client.server.received_messages.qsize() == 0
    fake_client.close()


@pytest.mark.parametrize('auth_type', ['PLAIN', 'LOGIN'])
def test_can_use_smtp_auth(auth_type):
    other_auth_types = {'PLAIN', 'LOGIN'} - {auth_type}
    socket_mock = SocketMock(authenticator=accept_any_login, auth_exclude_mechanism=other_auth_types)

    fake_client = fake_smtp_client(socket_mock=socket_mock)
    mailer = SMTPMailer(client=fake_client, username='foo', password='foo')
    message = b'Header: value\n\nbody\n'
    msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', message)

    assert msg_was_sent
    received_queue = fake_client.server.received_messages
    assert received_queue.qsize() == 1
    received_message = received_queue.get(block=False)
    assert received_message.username == 'foo'

@pytest.mark.parametrize('port, tls, expected_tls', [
    (25,  None,              TLSMode.OPPORTUNISTIC),
    (587, None,              TLSMode.OPPORTUNISTIC),
    (465, None,              TLSMode.IMPLICIT),
    (465, TLSMode.IMPLICIT,  TLSMode.IMPLICIT),
    (587, TLSMode.IMPLICIT,  TLSMode.IMPLICIT),
    (587, TLSMode.STARTTLS,  TLSMode.STARTTLS),
])
def test_smtpmailer_can_use_implicit_tls(port, tls, expected_tls):
    mailer = SMTPMailer('site.invalid', port=str(port), tls=tls)
    assert mailer.tls == expected_tls
    with mock.patch('schwarz.mailqueue.mailer.SMTPClient') as client_cls:
        mailer.init_smtp_client()
    _, kwargs = client_cls.call_args
    assert kwargs['implicit_tls'] == (expected_tls == TLSMode.IMPLICIT)

def test_smtpmailer_rejects_invalid_tls_setting():
    with pytest.raises(ValueError):
        SMTPMailer('site.invalid', tls='foo')

@pytest.mark.parametrize('tls', [TLSMode.STARTTLS, TLSMode.OPPORTUNISTIC])
def test_smtpmailer_always_uses_implicit_tls_for_port_465(tls):
    with pytest.raises(ValueError):
        SMTPMailer('site.invalid', port=465, tls=tls)

def test_smtpmailer_does_not_send_message_if_starttls_is_required_but_unsupported():
    # STARTTLS is not supported by the test server (no TLS context)
    fake_client = fake_smtp_client()
    logger, logs = build_collecting_logger()
    mailer = SMTPMailer(client=fake_client, tls=TLSMode.STARTTLS, smtp_log=logger)
    msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', b'Header: value\n\nbody\n')

    assert not msg_was_sent
    assert fake_client.server.received_messages.qsize() == 0
    log_msg, = [lr.getMessage() for lr in logs.buffer]
    assert 'STARTTLS' in log_msg

@pytest.mark.parametrize('tls_str, port, expected_tls', [
    ('yes',           '25',  TLSMode.STARTTLS),
    ('yes',           '587', TLSMode.STARTTLS),
    ('yes',           '465', TLSMode.IMPLICIT),
    ('implicit',      '587', TLSMode.IMPLICIT),
    ('opportunistic', '587', TLSMode.OPPORTUNISTIC),
    ('',              '587', TLSMode.OPPORTUNISTIC),
    ('',              '465', TLSMode.IMPLICIT),
])
def test_init_smtp_mailer_parses_tls_setting(tls_str, port, expected_tls):
    settings = {'smtp_hostname': 'site.invalid', 'smtp_port': port, 'smtp_tls': tls_str}
    mailer = init_smtp_mailer(settings)
    assert mailer.tls == expected_tls

@pytest.mark.parametrize('settings', [
    {'smtp_tls': 'foo'},
    {'smtp_tls': 'starttls'},
    {'smtp_tls': 'opportunistic', 'smtp_port': '465'},
    {'smtp_tls': 'yes', 'smtp_port': 'foo'},
])
def test_init_smtp_mailer_rejects_invalid_tls_setting(settings):
    settings['smtp_hostname'] = 'site.invalid'
    with pytest.raises(SystemExit) as exc_info:
        init_smtp_mailer(settings)
    assert exc_info.value.code == 31

@pytest.mark.parametrize('hostname, port, tls_str, expect_warning', [
    ('site.invalid', '587', None,            True),
    ('site.invalid', '587', '',              True),
    ('site.invalid', '587', 'opportunistic', False),
    ('site.invalid', '587', 'yes',           False),
    ('site.invalid', '465', None,            False),
    ('localhost',    '25',  None,            False),
    ('127.0.0.1',    '25',  None,            False),
    ('::1',          '25',  None,            False),
])
def test_init_smtp_mailer_warns_about_missing_tls_setting(hostname, port, tls_str, expect_warning):
    settings = {'smtp_hostname': hostname, 'smtp_port': port}
    if tls_str is not None:
        settings['smtp_tls'] = tls_str
    with mock.patch.object(logging.getLogger('mailqueue'), 'warning') as log_warning:
        init_smtp_mailer(settings)
    assert log_warning.called == expect_warning

# --- internal helpers ----------------------------------------------------
class RejectRecipientHandler(MessageCollector):
    def __init__(self, rejected_recipient):
        super().__init__()
        self.rejected_recipient = rejected_recipient

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if address == self.rejected_recipient:
            return '550 recipient rejected'
        envelope.rcpt_tos.append(address)
        return '250 OK'

def _build_overrides(**overrides):
    _overrides = {}
    for method_name, exception in overrides.items():
        def raise_exc():
            raise exception
        _overrides[method_name] = raise_exc
    return _overrides
