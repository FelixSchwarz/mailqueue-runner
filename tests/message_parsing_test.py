# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO

from pythonic_testcase import *

from schwarz.mailqueue import parse_message_envelope


class MessageParsingTest(PythonicTestCase):
    def test_can_parse_simple_message_envelope(self):
        queue_fp = self._msg_fp(
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
        queue_fp = self._msg_fp(return_path=b'<foo@site.example>')
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)

    def test_can_parse_encoded_header(self):
        # repoze.sendmail encodes all (envelope) header values
        queue_fp = self._msg_fp(
            return_path=b'=?utf-8?q?foo=40site=2Eexample?=',
            envelope_to=b'=?utf-8?q?foo=2Ebar=40site=2Eexample?=',
        )
        (from_addr, to_addrs, msg_fp) = parse_message_envelope(queue_fp)
        assert_equals('foo@site.example', from_addr)
        assert_equals(('foo.bar@site.example',), to_addrs)


    # --- internal helpers ----------------------------------------------------
    def _msg_fp(self, return_path=None, envelope_to=None, msg_bytes=None):
        if return_path is None:
            return_path = b'foo@site.example'
        if envelope_to is None:
            envelope_to = b'bar@site.example'
        if msg_bytes is None:
            msg_bytes = b'RFC-821 MESSAGE'
        msg = (
            b'Return-path: ' + return_path + b'\n'
            b'Envelope-to: ' + envelope_to + b'\n' + \
            msg_bytes
        )
        return BytesIO(msg)

