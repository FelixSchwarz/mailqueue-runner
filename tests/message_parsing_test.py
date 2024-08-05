# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from datetime import datetime as DateTime
from email.message import Message
from io import BytesIO

from boltons.timeutils import LocalTZ

from schwarz.mailqueue import parse_message_envelope, testutils
from schwarz.mailqueue.queue_runner import serialize_message_with_queue_data


def test_can_parse_simple_message_envelope():
    queue_fp = build_queued_message(
        sender='foo@site.example',
        recipient='bar@site.example',
        msg=b'RFC-821 MESSAGE',
    )
    msg_info = parse_message_envelope(queue_fp)
    assert msg_info.from_addr == 'foo@site.example'
    assert msg_info.to_addrs == ('bar@site.example',)
    assert msg_info.msg_fp.read() == b'RFC-821 MESSAGE'

def test_can_parse_return_path_with_angle_brackets():
    # Exim puts angle brackets around the return path
    queue_fp = build_queued_message(sender='foo@site.example')
    _assert_return_path_has_angle_brackets(queue_fp)
    msg_info = parse_message_envelope(queue_fp)
    assert msg_info.from_addr == 'foo@site.example'

def _assert_return_path_has_angle_brackets(queue_fp):
    sender_line = queue_fp.readline()
    queue_fp.seek(0)
    assert sender_line == b'Return-path: <foo@site.example>\n'

def test_can_parse_encoded_header():
    # repoze.sendmail encodes all (envelope) header values
    queue_fp = build_queued_message(
        sender='=?utf-8?q?foo=40site=2Eexample?=',
        recipient='=?utf-8?q?foo=2Ebar=40site=2Eexample?=',
    )
    msg_info = parse_message_envelope(queue_fp)
    assert msg_info.from_addr == 'foo@site.example'
    assert msg_info.to_addrs == ('foo.bar@site.example',)

def test_can_parse_message_with_utf8_data():
    msg = Message()
    msg['Message-ID'] = '<foo@id.example>'
    msg['Mime-Version'] = '1.0'
    msg['Content-Transfer-Encoding'] = '8bit'
    msg['Content-Type'] = 'text/plain; charset=UTF-8'
    msg.set_payload(b'some \xc2\xbbnon-ascii\xc2\xab text')

    queue_fp = build_queued_message(
        sender='foo@site.example',
        recipient='bar@site.example',
        msg=msg,
    )
    msg_info = parse_message_envelope(queue_fp)
    assert msg_info.from_addr == 'foo@site.example'
    assert msg_info.to_addrs == ('bar@site.example',)
    assert msg_info.msg_id == 'foo@id.example'
    assert msg_info.msg_fp.read() == msg.as_bytes()

def test_can_parse_queue_metadata():
    queue_date = DateTime(2020, 10, 1, hour=15, minute=42, second=21, tzinfo=LocalTZ)
    last_attempt = DateTime(2020, 10, 1, hour=16, minute=0, tzinfo=LocalTZ)
    retry_attempts = 3

    queue_fp = build_queued_message(
        sender='foo@site.example',
        recipient  = 'bar@site.example',
        queue_date = queue_date,
        last       = last_attempt,
        retries    = retry_attempts,
        msg=b'RFC-821 MESSAGE',
    )
    msg_info = parse_message_envelope(queue_fp)
    assert msg_info.from_addr == 'foo@site.example'
    assert msg_info.to_addrs == ('bar@site.example',)
    assert msg_info.queue_date == queue_date
    assert msg_info.last == last_attempt
    assert msg_info.retries == retry_attempts
    assert msg_info.msg_fp.read() == b'RFC-821 MESSAGE'


def build_queued_message(sender='foo@site.example', recipient='bar@site.example',
                         msg=None, queue_date=None, last=None, retries=None):
    if msg is None:
        msg = testutils.message()
    msg_bytes = serialize_message_with_queue_data(
        msg        = msg,
        sender     = sender,
        recipients = (recipient,),
        queue_date = queue_date,
        last       = last,
        retries    = retries,
    )
    return BytesIO(msg_bytes)
