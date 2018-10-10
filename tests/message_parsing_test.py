# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from pythonic_testcase import *

from schwarz.mailqueue import parse_message_envelope
from schwarz.mailqueue.testutils import build_queued_msg


class MessageParsingTest(PythonicTestCase):
    def test_can_parse_simple_message_envelope(self):
        queue_fp = build_queued_msg(
            return_path=b'foo@site.example',
            envelope_to=b'bar@site.example',
            msg_bytes=b'RFC-821 MESSAGE',
        )
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)
        assert_equals(('bar@site.example',), to_addrs)
        assert_equals(b'RFC-821 MESSAGE', msg_fp.read())

    def test_can_parse_return_return_path_with_angle_brackets(self):
        # Exim puts angle brackets around the return path
        queue_fp = build_queued_msg(return_path=b'<foo@site.example>')
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)

    def test_can_parse_encoded_header(self):
        # repoze.sendmail encodes all (envelope) header values
        queue_fp = build_queued_msg(
            return_path=b'=?utf-8?q?foo=40site=2Eexample?=',
            envelope_to=b'=?utf-8?q?foo=2Ebar=40site=2Eexample?=',
        )
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)
        assert_equals(('foo.bar@site.example',), to_addrs)

