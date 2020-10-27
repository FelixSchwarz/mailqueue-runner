# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals


__all__ = ['MQSignal']

class MQSignal(object):
    delivery_successful = 'mq:delivery_successful'  # (msg, send_result)
    delivery_failed     = 'mq:delivery_failed'      # (msg, send_result)

