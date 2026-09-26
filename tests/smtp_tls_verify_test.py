# SPDX-License-Identifier: MIT

import socket
import ssl
import threading
from pathlib import Path

import pytest
from schwarz.log_utils.testutils import build_collecting_logger

from schwarz.mailqueue import SMTPMailer, TLSMode, default_tls_verify, init_smtp_mailer
from schwarz.mailqueue.smtpclient import SMTPClient, create_ssl_context


# self-signed certificate for "localhost"/127.0.0.1 (valid for 100 years)
SELF_SIGNED_CERT = Path(__file__).parent / 'self-signed-localhost.pem'


@pytest.fixture
def tls_server():
    """Minimal SMTP server with implicit TLS: sends the greeting after the TLS
    handshake and closes the connection after the first command."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(SELF_SIGNED_CERT)
    listen_sock = socket.create_server(('127.0.0.1', 0))
    listen_sock.settimeout(5)

    def serve():
        try:
            sock, _ = listen_sock.accept()
        except OSError:
            return
        with sock:
            try:
                with context.wrap_socket(sock, server_side=True) as tls_sock:
                    tls_sock.sendall(b'220 localhost ESMTP\r\n')
                    tls_sock.recv(1024)
                    tls_sock.sendall(b'221 bye\r\n')
            except (ssl.SSLError, OSError):
                # client rejected the certificate
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listen_sock.getsockname()
    finally:
        listen_sock.close()
        thread.join(timeout=5)


def test_create_ssl_context_verifies_certificates_by_default():
    context = create_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname

def test_create_ssl_context_can_disable_verification():
    context = create_ssl_context(verify=False)
    assert context.verify_mode == ssl.CERT_NONE
    assert not context.check_hostname

def test_smtpclient_rejects_untrusted_certificate_by_default(tls_server):
    host, port = tls_server
    with pytest.raises(ssl.SSLCertVerificationError):
        SMTPClient(host, port, implicit_tls=True, timeout=5)

def test_smtpclient_can_skip_certificate_verification(tls_server):
    host, port = tls_server
    client = SMTPClient(host, port, implicit_tls=True, timeout=5,
                        ssl_context=create_ssl_context(verify=False))
    assert client.quit().code == 221

@pytest.mark.parametrize('tls_verify', [True, False])
def test_smtpmailer_uses_tls_verify_setting(tls_verify):
    mailer = SMTPMailer('site.invalid', tls_verify=tls_verify)
    assert mailer.tls_verify == tls_verify

def test_smtpmailer_does_not_send_message_if_certificate_is_untrusted(tls_server):
    host, port = tls_server
    logger, logs = build_collecting_logger()
    mailer = SMTPMailer(host, port=port, tls=TLSMode.IMPLICIT, timeout=5, smtp_log=logger)
    msg_was_sent = mailer.send('foo@site.example', 'bar@site.example', b'Header: value\n\nbody\n')

    assert not msg_was_sent
    warnings = [lr.getMessage() for lr in logs.buffer if lr.levelname == 'WARNING']
    assert len(warnings) == 1
    assert 'CERTIFICATE_VERIFY_FAILED' in warnings[0]

@pytest.mark.parametrize('tls_verify_str, expected', [
    (None,    True),
    ('',      True),
    ('yes',   True),
    ('no',    False),
    ('No',    False),
    ('false', False),
])
def test_init_smtp_mailer_parses_tls_verify_setting(tls_verify_str, expected):
    settings = {'smtp_hostname': 'site.invalid', 'smtp_tls': 'yes'}
    if tls_verify_str is not None:
        settings['smtp_tls_verify'] = tls_verify_str
    mailer = init_smtp_mailer(settings)
    assert mailer.tls_verify == expected

@pytest.mark.parametrize('hostname, tls, expected', [
    ('site.invalid', TLSMode.OPPORTUNISTIC, False),
    ('site.invalid', TLSMode.STARTTLS,      True),
    ('site.invalid', TLSMode.IMPLICIT,      True),
    ('localhost',    TLSMode.STARTTLS,      False),
    ('LocalHost',    TLSMode.IMPLICIT,      False),
    ('127.0.0.1',    TLSMode.STARTTLS,      False),
    ('::1',          TLSMode.IMPLICIT,      False),
])
def test_default_tls_verify(hostname, tls, expected):
    assert default_tls_verify(hostname, tls) == expected

@pytest.mark.parametrize('hostname, port, tls_str, tls_verify_str, expected', [
    # no explicit "smtp_tls_verify": see "default_tls_verify()"
    ('site.invalid', '587', None,            None,  False),
    ('site.invalid', '587', 'opportunistic', None,  False),
    ('site.invalid', '587', 'yes',           None,  True),
    ('site.invalid', '465', None,            None,  True),
    ('localhost',    '587', 'yes',           None,  False),
    ('127.0.0.1',    '465', None,            None,  False),
    # explicit settings always win
    ('site.invalid', '587', 'opportunistic', 'yes', True),
    ('localhost',    '587', 'yes',           'yes', True),
    ('site.invalid', '587', 'yes',           'no',  False),
])
def test_init_smtp_mailer_uses_tls_verify_heuristic(hostname, port, tls_str, tls_verify_str, expected):
    settings = {'smtp_hostname': hostname, 'smtp_port': port}
    if tls_str is not None:
        settings['smtp_tls'] = tls_str
    if tls_verify_str is not None:
        settings['smtp_tls_verify'] = tls_verify_str
    mailer = init_smtp_mailer(settings)
    assert mailer.tls_verify == expected

def test_init_smtp_mailer_rejects_invalid_tls_verify_setting():
    settings = {'smtp_hostname': 'site.invalid', 'smtp_tls_verify': 'maybe'}
    with pytest.raises(SystemExit) as exc_info:
        init_smtp_mailer(settings)
    assert exc_info.value.code == 31
