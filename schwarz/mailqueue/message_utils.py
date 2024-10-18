# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import calendar
import email.policy
import email.utils
import re
from datetime import datetime as DateTime, timedelta as TimeDelta, timezone
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesFeedParser, BytesHeaderParser
from io import BytesIO
from typing import BinaryIO, NamedTuple, Optional, Sequence

from boltons.timeutils import ConstantTZInfo, LocalTZ

from .lib import Result


__all__ = ['autogenerate_headers', 'dt_now', 'parse_message_envelope', 'MsgInfo', 'SendResult']

class SendResult(Result):
    def __init__(self, was_sent, queued=None, transport=None):
        super().__init__(was_sent, queued=queued, transport=transport, discarded=None)


def parse_message_envelope(fp):
    known_meta_headers = {
        'Return-path',
        'Envelope-to',
        'X-Queue-Date',
        'X-Last-Attempt',
        'X-Retries',
        'X-Queue-Meta-End',
    }

    parser = BytesFeedParser()
    parser._set_headersonly()
    while True:
        line = fp.readline()
        if line == b'':
            raise ValueError('Header "X-Queue-Meta-End" not found.')
        parser.feed(line)
        if line.startswith(b'X-Queue-Meta-End: '):
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


class _MsgInfo(NamedTuple):
    from_addr  : str
    to_addrs   : Sequence
    msg_fp     : BinaryIO
    queue_date : Optional[DateTime]
    last       : Optional[DateTime]
    retries    : int = 0


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
        msg_headers = BytesHeaderParser().parse(self.msg_fp, headersonly=True)
        msg_id_value = msg_headers['Message-ID']
        self.msg_fp.seek(old_pos)
        # message ids are usually enclosed in angle brackets but these do NOT
        # belong to the message id.
        return strip_brackets(msg_id_value)

    @property
    def msg_bytes(self):
        old_pos = self.msg_fp.tell()
        self.msg_fp.seek(0)
        data = self.msg_fp.read()
        self.msg_fp.seek(old_pos)
        return data


_re_angle_brackets = re.compile(br'^<?(.+?)>?$')
_re_angle_brackets_str = re.compile('^<?(.+?)>?$')
_re_header_list = re.compile(r'\s*,\s*')


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
    if isinstance(value, bytes):
        angle_regex = _re_angle_brackets
    else:
        angle_regex = _re_angle_brackets_str
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
    return int(re.search(r'^(\d+)$', number_str).group(1))

def msg_as_bytes(msg) -> bytes:
    """
    Convert a message-like instance to bytes. In particular, it uses an
    SMTP-compatible serialization with CRLF line endings ("\r\n") instead of
    plain "\n".
    See also: https://github.com/python/cpython/issues/42554
    """
    if hasattr(msg, 'as_bytes'):
        # email.Message
        return msg.as_bytes(policy=email.policy.SMTP)
    if hasattr(msg, 'read'):
        msg_bytes = msg.read()
    elif isinstance(msg, bytes):
        # LATER: check if message is CLRF-terminated
        msg_bytes = msg
    else:
        raise ValueError('"msg" must be an email.Message, bytes or a file-like object.')
    return msg_bytes


def autogenerate_headers(
        input_headers,
        set_date_header, set_from_header, set_msgid_header,
        set_to_header,
        msg_sender,
        recipients,
    ) -> bytes:
    extra_headers = EmailMessage()
    input_msg_date = input_headers.get('Date')
    if set_date_header and not input_msg_date:
        extra_headers['Date'] = email.utils.format_datetime(DateTime.now(timezone.utc))
    input_msg_from = input_headers.get('From')
    if set_from_header and not input_msg_from:
        extra_headers['From'] = msg_sender
    input_msg_to = input_headers.get('To')
    if set_to_header and (not input_msg_to) and recipients:
        extra_headers['To'] = ', '.join(recipients)
    input_msg_id = input_headers.get('Message-ID')
    if set_msgid_header and not input_msg_id:
        _, smtp_sender_domain = msg_sender.split('@', 1)
        extra_headers['Message-ID'] = email.utils.make_msgid(domain=smtp_sender_domain)

    prepended_header_lines = b''
    if extra_headers:
        fake_msg_bytes = msg_as_bytes(extra_headers)
        prepended_header_lines = fake_msg_bytes.split(b'\r\n\r\n', 1)[0] + b'\r\n'
    return prepended_header_lines
