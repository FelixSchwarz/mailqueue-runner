# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os
import sys


__all__ = [
    'configparser',
    'os_makedirs',
    'queue',
    'FileNotFoundError',
    'IS_PYTHON3',
]

IS_PYTHON3 = (sys.version_info >= (3,0))

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

