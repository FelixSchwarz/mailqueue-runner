# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from collections import namedtuple
from email.header import decode_header
from email.parser import HeaderParser
from io import BytesIO, TextIOWrapper
import re


__all__ = ['parse_message_envelope']

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
            from_addr = decode_header_value(strip_brackets(header_value))
        elif header_name == b'Envelope-to':
            to_addrs = parse_envelope_addrs(decode_header_value(header_value))
        else:
            msg_bytes += line
        if (from_addr is not None) and (to_addrs is not None):
            break

    msg_fp = BytesIO(msg_bytes + fp.read())
    msg_fp.seek(0)
    msg_info = MsgInfo(from_addr, tuple(to_addrs), msg_fp)
    return msg_info



_MsgInfo = namedtuple('_MsgInfo', ('from_addr', 'to_addrs', 'msg_fp'))

class MsgInfo(_MsgInfo):
    @property
    def msg_id(self):
        old_pos = self.msg_fp.tell()
        self.msg_fp.seek(0)
        # Unfortunately Python's TextIOWrapper always closes wrapped files:
        #    https://bugs.python.org/issue21363
        msg_str_fp = TextIOWrapper(UnclosableWrapper(self.msg_fp), encoding='ascii')
        msg_headers = HeaderParser().parse(msg_str_fp, headersonly=True)
        # message ids are usually enclosed in angle brackets but these do NOT
        # belong to the message id.
        msg_id_value = msg_headers['Message-ID']
        self.msg_fp.seek(old_pos)
        return strip_brackets(msg_id_value)

    @property
    def msg_bytes(self):
        old_pos = self.msg_fp.tell()
        self.msg_fp.seek(0)
        data = self.msg_fp.read()
        self.msg_fp.seek(old_pos)
        return data


class UnclosableWrapper(object):
    def __init__(self, wrapped_instance):
        self.wrapped_instance = wrapped_instance

    def __getattr__(self, name):
        return getattr(self.wrapped_instance, name)

    def close(self):
        pass



_re_header = re.compile(br'^(\S+):\s*(\S+)\s*$')
_re_angle_brackets = re.compile(br'^<?(.+?)>?$')
_re_angle_brackets_str = re.compile('^<?(.+?)>?$')
_re_header_list = re.compile(r'\s*,\s*')

def read_header_line(fp):
    return fp.readline()

def decode_header_value(header_bytes):
    encoded_str = header_bytes.decode('ASCII')
    header_str = ''
    for part_bytes, charset in decode_header(encoded_str):
        if charset is None:
            assert isinstance(part_bytes, str)
            header_str += part_bytes
        else:
            header_str += part_bytes.decode(charset)
    return header_str

def strip_brackets(value):
    if value is None:
        return None
    angle_regex = _re_angle_brackets if isinstance(value, bytes) else _re_angle_brackets_str
    match = angle_regex.search(value)
    return match.group(1)

def parse_envelope_addrs(header_str):
    return _re_header_list.split(header_str)

