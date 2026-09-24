# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from schwarz.mailqueue.testutils import FakeSSLContext, fake_smtp_client


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
