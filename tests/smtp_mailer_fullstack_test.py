# SPDX-License-Identifier: MIT

from types import SimpleNamespace

import pytest

from schwarz.mailqueue import SMTPMailer
from schwarz.mailqueue.testutils import SMTPTestServer


@pytest.fixture
def ctx():
    mta = SMTPTestServer()
    mta.start()
    ctx = {
        'hostname': mta.hostname,
        'listen_port': mta.port,
        'mta': mta,
    }
    try:
        yield SimpleNamespace(**ctx)
    finally:
        mta.stop()


def test_can_send_message(ctx):
    mailer = SMTPMailer(ctx.hostname, port=ctx.listen_port)
    fromaddr = 'foo@site.example'
    message = b'Header: value\n\nbody\n'
    toaddrs = ('bar@site.example', 'baz@site.example',)
    msg_was_sent = mailer.send(fromaddr, toaddrs, message)

    assert msg_was_sent
    received_queue = ctx.mta.received_messages
    assert received_queue.qsize() == 1
    received_message = received_queue.get(block=False)
    assert received_message.smtp_from == fromaddr
    assert tuple(received_message.smtp_to) == toaddrs
    assert received_message.username is None
    # The message is sent with CRLF line endings.
    assert received_message.msg_bytes == b'Header: value\r\n\r\nbody\r\n'
