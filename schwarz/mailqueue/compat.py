# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import os


__all__ = [
    'IS_WINDOWS',
]

IS_WINDOWS = (os.name == 'nt')
