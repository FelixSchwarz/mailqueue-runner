# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import email.utils
import os
import sys


__all__ = [
    'configparser',
    'format_datetime_rfc2822',
    'make_msgid',
    'os_makedirs',
    'queue',
    'FileNotFoundError',
    'IS_PYTHON3',
    'IS_WINDOWS',
]

IS_PYTHON3 = (sys.version_info >= (3,0))
IS_WINDOWS = (os.name == 'nt')

def os_makedirs(name, mode, exist_ok=False):
    if IS_PYTHON3:
        os.makedirs(name, mode, exist_ok=exist_ok)
        return
    # Python 2 version with "exist_ok=True" is racy but that is ok with my
    # as Python 2 won't last that long.
    if exist_ok is False:
        os.makedirs(name, mode)
    elif not os.path.exists(name):
        os.makedirs(name, mode)

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

try:
    import queue
except ImportError:
    import Queue as queue

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = OSError
else:
    FileNotFoundError = FileNotFoundError


def format_datetime_rfc2822(dt):
    try:
        date_str = email.utils.format_datetime(dt)
    except AttributeError:
        # Python 2
        # email.utils.formatdate() in Python always uses UTC timezone ("-0000")
        # so the resulting string points to the same time but possibly in a
        # different timezone.
        # The naive version might something like
        #   now_time = time.mktime(dt.timetuple())
        #   date_str = email.utils.formatdate(now_time)
        date_str = format_datetime_py2(dt)
    return date_str


WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
MONTHS = (None, 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

def format_datetime_py2(dt):
    tt = dt.timetuple()
    utc_offset_str = dt.strftime('%z')
    pattern = '%s, %02d %s %d %02d:%02d:%02d %s'
    return  pattern % (
        WEEKDAYS[tt.tm_wday],
        tt.tm_mday,
        MONTHS[tt.tm_mon],
        tt.tm_year,
        tt.tm_hour,
        tt.tm_min,
        tt.tm_sec,
        utc_offset_str
    )


def make_msgid(domain=None):
    if not domain:
        return email.utils.make_msgid()
    if sys.version_info >= (3, 2):
        return email.utils.make_msgid(domain=domain)

    msg_id_str = email.utils.make_msgid('@'+domain)
    msg_id = msg_id_str.rsplit('@', 1)[0] + '>'
    return msg_id

