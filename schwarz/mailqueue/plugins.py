# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from schwarz.puzzle_plugins import SignalRegistry


__all__ = ['registry', 'MQAction', 'MQSignal']

registry = SignalRegistry()

class MQSignal(object):
    delivery_successful = 'mq:delivery_successful'  # (msg, send_result)
    delivery_failed     = 'mq:delivery_failed'      # (msg, send_result)

class MQAction(object):
    DISCARD = 'discard'
