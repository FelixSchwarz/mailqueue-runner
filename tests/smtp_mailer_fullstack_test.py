# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import pytest
from dotmap import DotMap
from pymta.test_util import SMTPTestHelper

from schwarz.mailqueue import SMTPMailer


@pytest.fixture
def ctx():
    mta_helper = SMTPTestHelper()
    (hostname, listen_port) = mta_helper.start_mta()
    ctx = {
        'hostname': hostname,
        'listen_port': listen_port,
        'mta': mta_helper,
    }
    try:
        yield DotMap(_dynamic=False, **ctx)
    finally:
        mta_helper.stop_mta()


def test_can_send_message(ctx):
    mailer = SMTPMailer(ctx.hostname, port=ctx.listen_port)
    fromaddr = 'foo@site.example'
    message = b'Header: value\n\nbody\n'
    toaddrs = ('bar@site.example', 'baz@site.example',)
    msg_was_sent = mailer.send(fromaddr, toaddrs, message)

    assert msg_was_sent
    received_queue = ctx.mta.get_received_messages()
    assert received_queue.qsize() == 1
    received_message = received_queue.get(block=False)
    assert received_message.smtp_from == fromaddr
    assert tuple(received_message.smtp_to) == toaddrs
    assert received_message.username is None
    # pymta converts this to a string automatically
    expected_message = message.decode('ASCII')
    assert received_message.msg_data == expected_message
