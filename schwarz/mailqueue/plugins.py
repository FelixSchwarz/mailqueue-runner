# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT


__all__ = [
    'registry', 'MQAction', 'MQSignal',
    'parse_list_str',
    'PluginLoader',
]

try:
    from schwarz.puzzle_plugins import PluginLoader, SignalRegistry, parse_list_str
except ImportError:
    registry = None
    PluginLoader = None
    parse_list_str = None
else:
    registry = SignalRegistry()


class MQSignal(object):
    delivery_successful = 'mq:delivery_successful'  # (msg, send_result)
    delivery_failed     = 'mq:delivery_failed'      # (msg, send_result)

class MQAction(object):
    DISCARD = 'discard'
