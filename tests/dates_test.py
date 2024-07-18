# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime as DateTime, timedelta as TimeDelta

import pytest
from boltons.timeutils import ZERO, ConstantTZInfo

from schwarz.mailqueue.compat import format_datetime_rfc2822
from schwarz.mailqueue.message_utils import parse_datetime


@pytest.mark.parametrize('dt', [
    DateTime(2020, 3, 1, hour=11, minute=42, second=23, tzinfo=ConstantTZInfo(offset=TimeDelta(hours=1))),  # noqa: E501 (line too long)
    DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=ConstantTZInfo(offset=TimeDelta(hours=2))),  # noqa: E501 (line too long)
    DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=ConstantTZInfo(offset=TimeDelta(hours=6))),  # noqa: E501 (line too long)
    DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=ConstantTZInfo(offset=ZERO)),
])
def test_parse_datetime(dt):
    dt_str = format_datetime_rfc2822(dt)
    assert parse_datetime(dt_str) == dt

@pytest.mark.parametrize('offset_str, offset', [
    ('-0500', -(5*60)),
    ('-0445', -(4*60 + 45)),
])
def test_format_datetime_rfc2822(offset_str, offset):
    offset_td = TimeDelta(minutes=offset)
    tz = ConstantTZInfo(offset=offset_td)
    dt = DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=tz)
    expected_str = 'Tue, 21 Jul 2020 23:02:59 ' + offset_str
    assert format_datetime_rfc2822(dt) == expected_str
