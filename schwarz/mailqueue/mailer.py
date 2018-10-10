# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals


__all__ = ['DebugMailer']

class DebugMailer(object):
    def __init__(self, simulate_failed_sending=False):
        self.simulate_failed_sending = simulate_failed_sending
        self.sent_mails = []

    def send(self, fromaddr, toaddrs, message):
        if self.simulate_failed_sending:
            return False
        self.sent_mails.append((fromaddr, toaddrs, message))
        return True

