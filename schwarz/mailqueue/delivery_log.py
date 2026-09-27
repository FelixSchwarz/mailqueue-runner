# SPDX-License-Identifier: MIT

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from datetime import timedelta as TimeDelta

    from smtpproto.protocol import SMTPResponse


__all__ = ['DeliveryEvent', 'format_delay', 'format_logfmt', 'format_smtp_response']

STATUS_WIDTH = len('discarded')

_re_needs_quoting = re.compile(r'[\s"=\\]|[\x00-\x1f\x7f]')
_re_escape = re.compile(r'["\\]|[\x00-\x1f\x7f]')
_escapes = {'"': '\\"', '\\': '\\\\', '\n': '\\n', '\r': '\\r', '\t': '\\t'}


@dataclass(frozen=True)
class DeliveryEvent:
    # order of fields here is used to assemble the logged line.
    status: str
    to: str
    msgid: str | None = None
    via: str | None = None
    from_addr: str | None = None
    attempts: int | None = None
    delay: str | None = None
    app: str | None = None
    smtp: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, str | int]:
        """Return the log fields (in log order), skipping `None` values."""
        logged_fields: dict[str, str | int] = {}
        for field in dataclasses.fields(DeliveryEvent):
            logged_attr = field.name if field.name != 'from_addr' else 'from'
            value = getattr(self, field.name)
            if value is None:
                continue
            logged_fields[logged_attr] = value
        return logged_fields


def format_logfmt(event: DeliveryEvent) -> str:
    """
    Return the delivery `event` as a single line of "key=value" pairs (logfmt),
    which is easy to read for humans and can also be parsed by common log tools.
    """
    parts = []
    for key, value in event.as_dict().items():
        value_str = _quote(str(value))
        if key == 'status':
            # Pad status field to a fixed width so the following fields line up
            # across lines. This hopefully improves readability for humans.
            value_str = value_str.ljust(STATUS_WIDTH)
        parts.append('%s=%s' % (key, value_str))
    return ' '.join(parts)

def format_delay(delay: TimeDelta) -> str:
    seconds = max(int(delay.total_seconds()), 0)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return '%dd%dh' % (days, hours)
    elif hours:
        return '%dh%02dm' % (hours, minutes)
    elif minutes:
        return '%dm' % minutes
    return '%ds' % seconds

def format_smtp_response(response: SMTPResponse) -> str:
    # multi-line responses are joined with "\n" by smtpproto
    message = ' '.join(response.message.splitlines())
    return f'{response.code:d} {message}'.rstrip()


def _quote(value: str) -> str:
    if value and not _re_needs_quoting.search(value):
        return value
    return '"%s"' % _re_escape.sub(_escape, value)

def _escape(m) -> str:
    return _escapes.get(m.group(0)) or '\\x%02x' % ord(m.group(0))
