# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime as DateTime
from io import BytesIO

from boltons.timeutils import LocalTZ
from pythonic_testcase import *

from schwarz.mailqueue import parse_message_envelope, testutils
from schwarz.mailqueue.queue_runner import serialize_message_with_queue_data


class MessageParsingTest(PythonicTestCase):
    def test_can_parse_simple_message_envelope(self):
        queue_fp = build_queued_message(
            sender='foo@site.example',
            recipient='bar@site.example',
            msg=b'RFC-821 MESSAGE',
        )
        msg_info = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', msg_info.from_addr)
        assert_equals(('bar@site.example',), msg_info.to_addrs)
        assert_equals(b'RFC-821 MESSAGE', msg_info.msg_fp.read())

    def test_can_parse_return_path_with_angle_brackets(self):
        # Exim puts angle brackets around the return path
        queue_fp = build_queued_message(sender='foo@site.example')
        self._assert_return_path_has_angle_brackets(queue_fp)
        msg_info = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', msg_info.from_addr)

    def _assert_return_path_has_angle_brackets(self, queue_fp):
        sender_line = queue_fp.readline()
        queue_fp.seek(0)
        assert_equals(b'Return-path: <foo@site.example>\n', sender_line)

    def test_can_parse_encoded_header(self):
        # repoze.sendmail encodes all (envelope) header values
        queue_fp = build_queued_message(
            sender='=?utf-8?q?foo=40site=2Eexample?=',
            recipient='=?utf-8?q?foo=2Ebar=40site=2Eexample?=',
        )
        msg_info = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', msg_info.from_addr)
        assert_equals(('foo.bar@site.example',), msg_info.to_addrs)

    def test_can_parse_queue_metadata(self):
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
        assert_equals('foo@site.example', msg_info.from_addr)
        assert_equals(('bar@site.example',), msg_info.to_addrs)
        assert_equals(queue_date, msg_info.queue_date)
        assert_equals(last_attempt, msg_info.last)
        assert_equals(retry_attempts, msg_info.retries)
        assert_equals(b'RFC-821 MESSAGE', msg_info.msg_fp.read())


def build_queued_message(sender='foo@site.example', recipient='bar@site.example', msg=None, queue_date=None, last=None, retries=None):
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

