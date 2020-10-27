# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import calendar
from collections import namedtuple
from datetime import datetime as DateTime, timedelta as TimeDelta
from email.header import decode_header
from email.parser import FeedParser, HeaderParser
import email.utils
from io import BytesIO, TextIOWrapper
import re

from boltons.timeutils import ConstantTZInfo, LocalTZ

from .lib import Result


__all__ = ['dt_now', 'parse_message_envelope', 'MsgInfo', 'SendResult']

def SendResult(was_sent, queued=None, transport=None):
    return Result(was_sent, queued=queued, transport=transport, discarded=None)


def parse_message_envelope(fp):
    known_meta_headers = {
        'Return-path',
        'Envelope-to',
        'X-Queue-Date',
        'X-Last-Attempt',
        'X-Retries',
        'X-Queue-Meta-End',
    }

    parser = FeedParser()
    parser._headersonly = True
    while True:
        line = read_header_line(fp)
        if line == b'':
            raise ValueError('Header "X-Queue-Meta-End" not found.')
        # similar to Python's BytesFeedParser (Python 3.3+)
        line_str = line.decode('ascii', 'surrogateescape')
        parser.feed(line_str)
        if 'X-Queue-Meta-End' in line_str:
            break
    meta_msg = parser.close()
    queue_meta = dict(meta_msg.items())
    unknown_headers = set(queue_meta).difference(known_meta_headers)
    assert len(unknown_headers) == 0, unknown_headers

    b_return_path = queue_meta.pop('Return-path')
    from_addr = decode_header_value(strip_brackets(b_return_path))
    b_envelope_to = queue_meta.pop('Envelope-to')
    to_addrs = parse_envelope_addrs(decode_header_value(b_envelope_to))

    queue_date = parse_datetime(queue_meta.pop('X-Queue-Date'))
    last = parse_datetime(queue_meta.pop('X-Last-Attempt', None))

    retries = parse_number(queue_meta.pop('X-Retries', None))

    msg_fp = BytesIO(fp.read())
    msg_fp.seek(0)
    msg_info = MsgInfo(from_addr, tuple(to_addrs), msg_fp, queue_date, last=last, retries=retries)
    return msg_info


def dt_now():
    return DateTime.now(tz=LocalTZ)


_MsgInfo = namedtuple('_MsgInfo', ('from_addr', 'to_addrs', 'msg_fp', 'queue_date', 'last', 'retries'))

class MsgInfo(_MsgInfo):
    def __new__(cls, from_addr, to_addrs, msg_fp, queue_date=None, last=None, retries=None):
        self = _MsgInfo.__new__(cls,
            from_addr  = from_addr,
            to_addrs   = to_addrs,
            msg_fp     = msg_fp,
            queue_date = queue_date or DateTime.now(tz=LocalTZ),
            last       = last,
            retries    = retries or 0,
        )
        return self

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



_re_angle_brackets = re.compile(br'^<?(.+?)>?$')
_re_angle_brackets_str = re.compile('^<?(.+?)>?$')
_re_header_list = re.compile(r'\s*,\s*')

def read_header_line(fp):
    return fp.readline()

def decode_header_value(encoded_str):
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

def parse_datetime(dt_str):
    if not dt_str:
        return None
    parsed_tuple = email.utils.parsedate_tz(dt_str)
    # last item is the UTC offset, need to handle that separately
    ts = calendar.timegm(parsed_tuple[:9])
    utc_offset_s = parsed_tuple[9]

    utc_offset = TimeDelta(seconds=utc_offset_s)
    tz = ConstantTZInfo(offset=utc_offset)
    dt = DateTime.utcfromtimestamp(ts).replace(tzinfo=tz)
    return dt

def parse_number(number_str):
    if number_str is None:
        return None
    return int(re.search('^(\d+)$', number_str).group(1))

def msg_as_bytes(msg):
    if hasattr(msg, 'as_bytes'):
        msg_bytes = msg.as_bytes()
    elif hasattr(msg, 'read'):
        msg_bytes = msg.read()
    elif hasattr(msg, 'as_string'):
        # email.message.Message in Python 2
        msg_bytes = msg.as_string().encode('ascii')
    else:
        msg_bytes = msg
    return msg_bytes

