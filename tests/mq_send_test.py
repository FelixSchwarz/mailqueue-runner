# SPDX-License-Identifier: MIT

import email
import re
from types import SimpleNamespace

import pytest

from schwarz.mailqueue.cli import send_test_message_main
from schwarz.mailqueue.testutils import SMTPTestServer, create_ini


# prevent nosetests from running this imported function as "test"
send_test_message_main.__test__ = False


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

def test_mq_send_test_can_send_test_message(ctx, tmp_path):
    config_path = create_ini(ctx.hostname, ctx.listen_port, dir_path=str(tmp_path))

    cmd = [
        'mq-send-test',
        f'--config={config_path}',
        '--quiet',
        '--from=bar@site.example',
        '--to=foo@site.example',
    ]
    rc = send_test_message_main(argv=cmd, return_rc_code=True)
    assert rc == 0

    received_queue = ctx.mta.received_messages
    assert received_queue.qsize() == 1
    smtp_msg = received_queue.get(block=False)
    assert smtp_msg.smtp_from == 'bar@site.example'
    assert tuple(smtp_msg.smtp_to) == ('foo@site.example',)
    assert smtp_msg.username is None
    msg = email.message_from_bytes(smtp_msg.msg_bytes)
    assert msg['Subject'].startswith('Test message')
    assert_matches('^<[^@>]+@mqrunner.example>$', msg['Message-ID'],
        message='test message should use custom Msg-ID domain (with correct brackets)')


def assert_matches(pattern, text_str, message=None):
    match = re.match(pattern, text_str)
    assert match is not None, message
