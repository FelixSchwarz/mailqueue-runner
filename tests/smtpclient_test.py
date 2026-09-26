# SPDX-License-Identifier: MIT

import pytest

from schwarz.mailqueue.testutils import FakeSSLContext, SocketMock, fake_smtp_client


def test_does_not_use_tls_by_default():
    ssl_context = FakeSSLContext()
    client = fake_smtp_client(ssl_context=ssl_context)
    client.ehlo('client.example')
    client.quit()
    assert ssl_context.wrapped == []

def test_can_use_implicit_tls():
    ssl_context = FakeSSLContext()
    client = fake_smtp_client(implicit_tls=True, ssl_context=ssl_context)
    sock, server_hostname, is_pristine = ssl_context.wrapped[0]
    assert len(ssl_context.wrapped) == 1
    assert sock is client.server
    assert server_hostname == 'site.invalid'
    # TLS handshake must happen before the server greeting is read
    assert is_pristine

    client.sendmail('foo@site.example', 'bar@site.example', b'Header: value\r\n\r\nbody\r\n')
    client.quit()
    assert client.server.received_messages.qsize() == 1

@pytest.mark.parametrize('msg, expected_data', [
    (b'Header: value\r\n\r\nbody\r\n',   b'Header: value\r\n\r\nbody\r\n.\r\n'),
    (b'Header: value\n\nbody\n',         b'Header: value\r\n\r\nbody\r\n.\r\n'),
    (b'Header: value\r\rbody',           b'Header: value\r\n\r\nbody\r\n.\r\n'),
    (b'Header: value\r\n\r\n.body\n.\n', b'Header: value\r\n\r\n..body\r\n..\r\n.\r\n'),
])
def test_sends_message_with_crlf_line_endings(msg, expected_data):
    socket_mock = RecordingSocketMock()
    client = fake_smtp_client(socket_mock=socket_mock)
    client.sendmail('foo@site.example', 'bar@site.example', msg)
    assert socket_mock.sent_data.endswith(b'DATA\r\n' + expected_data)

@pytest.mark.parametrize('smuggling_sequence', [b'\n.\r\n', b'\r\n.\n', b'\n.\n', b'\r.\r\n'])
def test_prevents_smtp_smuggling(smuggling_sequence):
    # see https://www.postfix.org/smtp-smuggling.html
    socket_mock = RecordingSocketMock()
    client = fake_smtp_client(socket_mock=socket_mock)
    smuggled_msg = b'MAIL FROM:<admin@site.example>\r\nRCPT TO:<victim@site.example>\r\n'
    msg = b'Header: value\r\n\r\nbody' + smuggling_sequence + smuggled_msg
    client.sendmail('foo@site.example', 'bar@site.example', msg)

    data = socket_mock.sent_data.split(b'DATA\r\n', 1)[1]
    # only the final "end of data" sequence may be present
    assert data.count(b'\r\n.\r\n') == 1
    assert data.endswith(b'\r\n.\r\n')
    assert b'\r\n..\r\n' in data
    assert socket_mock.received_messages.qsize() == 1

# --- internal helpers ----------------------------------------------------
class RecordingSocketMock(SocketMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent_data = b''

    def sendall(self, data):
        self.sent_data += data
        super().sendall(data)
