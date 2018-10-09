# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from email.header import decode_header
from io import BytesIO
import re
import sys


__all__ = ['parse_message_envelope']

IS_PYTHON3 = (sys.version_info >= (3,0))
if IS_PYTHON3:
    unicode = str

def parse_message_envelope(fp):
    from_addr = None
    to_addrs = None
    msg_bytes = b''

    while True:
        line = read_header_line(fp)
        match = _re_header.search(line)
        header_name = match.group(1)
        header_value = match.group(2)
        if header_name == b'Return-path':
            from_addr = strip_brackets(decode_header_value(header_value))
        elif header_name == b'Envelope-to':
            to_addrs = parse_envelope_addrs(decode_header_value(header_value))
        else:
            msg_bytes += line
        if (from_addr is not None) and (to_addrs is not None):
            break

    msg_fp = BytesIO(msg_bytes + fp.read())
    return (from_addr, tuple(to_addrs), msg_fp)


_re_header = re.compile(b'^(\S+):\s*(\S+)\s*$')
_re_angle_brackets = re.compile('^<?(.+?)>?$')
_re_header_list = re.compile('\s*,\s*')

def read_header_line(fp):
    return fp.readline()

def decode_header_value(header_bytes):
    encoded_str = header_bytes.decode('ASCII')
    header_str = ''
    for part_bytes, charset in decode_header(encoded_str):
        if charset is None:
            assert isinstance(part_bytes, unicode)
            header_str += part_bytes
        else:
            header_str += part_bytes.decode(charset)
    return header_str

def strip_brackets(addr_str):
    match = _re_angle_brackets.search(addr_str)
    return match.group(1)

def parse_envelope_addrs(header_str):
    return _re_header_list.split(header_str)
