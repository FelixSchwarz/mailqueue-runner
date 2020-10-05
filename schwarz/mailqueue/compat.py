# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import email.utils
import os
import sys
import time


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
        now_time = time.mktime(dt.timetuple())
        date_str = email.utils.formatdate(now_time)
    return date_str


def make_msgid(domain=None):
    if not domain:
        return email.utils.make_msgid()
    if sys.version_info >= (3, 2):
        return email.utils.make_msgid(domain=domain)

    msg_id_str = email.utils.make_msgid('@'+domain)
    msg_id = msg_id_str.rsplit('@', 1)[0] + '>'
    return msg_id

