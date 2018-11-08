# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO

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
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)
        assert_equals(('bar@site.example',), to_addrs)
        assert_equals(b'RFC-821 MESSAGE', msg_fp.read())

    def test_can_parse_return_path_with_angle_brackets(self):
        # Exim puts angle brackets around the return path
        queue_fp = build_queued_message(sender='foo@site.example')
        self._assert_return_path_has_angle_brackets(queue_fp)
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)

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
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)
        assert_equals(('foo.bar@site.example',), to_addrs)


def build_queued_message(sender='foo@site.example', recipient='bar@site.example', msg=None):
    if msg is None:
        msg = testutils.message()
    msg_bytes = serialize_message_with_queue_data(
        msg=msg,
        sender=sender,
        recipient=recipient,
    )
    return BytesIO(msg_bytes)

