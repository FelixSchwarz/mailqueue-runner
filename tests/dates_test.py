# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime as DateTime, timedelta as TimeDelta

from boltons.timeutils import ConstantTZInfo, ZERO
from ddt import ddt as DataDrivenTestCase, data as ddt_data
from pythonic_testcase import *

from schwarz.mailqueue.compat import format_datetime_rfc2822
from schwarz.mailqueue.message_utils import parse_datetime


@DataDrivenTestCase
class DatesTest(PythonicTestCase):
    @ddt_data(
        DateTime(2020, 3, 1, hour=11, minute=42, second=23, tzinfo=ConstantTZInfo(offset=TimeDelta(hours=1))),
        DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=ConstantTZInfo(offset=TimeDelta(hours=2))),
        DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=ConstantTZInfo(offset=TimeDelta(hours=6))),
        DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=ConstantTZInfo(offset=ZERO)),
    )
    def test_parse_datetime(self, dt):
        dt_str = format_datetime_rfc2822(dt)
        assert_equals(dt, parse_datetime(dt_str))

    @ddt_data(
        ('-0500', -(5*60)),
        ('-0445', -(4*60 + 45)),
    )
    def test_format_datetime_rfc2822(self, d):
        offset_str, offset = d
        offset_td = TimeDelta(minutes=offset)
        tz = ConstantTZInfo(offset=offset_td)
        dt = DateTime(2020, 7, 21, hour=23, minute=2, second=59, tzinfo=tz)
        expected_str = 'Tue, 21 Jul 2020 23:02:59 ' + offset_str
        assert_equals(expected_str, format_datetime_rfc2822(dt))

