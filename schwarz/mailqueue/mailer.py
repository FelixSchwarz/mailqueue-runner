# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from .smtpclient import SMTPClient


__all__ = ['DebugMailer', 'SMTPMailer']

class SMTPMailer(object):
    def __init__(self, hostname=None, **kwargs):
        if (hostname is None) and ('connection' not in kwargs):
            raise TypeError('not enough parameters for __init__(): please specify at least "hostname" or "connection"')
        self.hostname = hostname
        self.port = kwargs.pop('port', 25)
        self.username = kwargs.pop('username', None)
        self.password = kwargs.pop('password', None)
        self.connect_timeout = kwargs.pop('timeout', 10)
        self._connection = kwargs.pop('connection', None)
        if kwargs:
            extra_name = tuple(kwargs)[0]
            raise TypeError("__init__() got an unexpected keyword argument '%s'" % extra_name)

    def connect(self):
        return SMTPClient(self.hostname, self.port, timeout=self.connect_timeout)

    def send(self, fromaddr, toaddrs, message):
        if self._connection is None:
            connection = self.connect()
        else:
            connection = self._connection
        connection.ehlo()

        is_tls_supported = connection.has_extn('starttls')
        if is_tls_supported:
            connection.starttls()
            connection.ehlo()
        if (self.username is not None) and (self.password is not None):
            connection.login(self.username, self.password)

        connection.sendmail(fromaddr, toaddrs, message)
        connection.quit()
        return True


class DebugMailer(object):
    def __init__(self, simulate_failed_sending=False):
        self.simulate_failed_sending = simulate_failed_sending
        self.sent_mails = []

    def send(self, fromaddr, toaddrs, message):
        if self.simulate_failed_sending:
            return False
        self.sent_mails.append((fromaddr, toaddrs, message))
        return True

