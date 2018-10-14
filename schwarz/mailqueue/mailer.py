# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from smtplib import SMTPException

from .smtpclient import SMTPClient


__all__ = ['DebugMailer', 'SMTPMailer']

class SMTPMailer(object):
    def __init__(self, hostname=None, **kwargs):
        if (hostname is None) and ('client' not in kwargs):
            raise TypeError('not enough parameters for __init__(): please specify at least "hostname" or "client"')
        self.hostname = hostname
        self.port = kwargs.pop('port', 25)
        self.username = kwargs.pop('username', None)
        self.password = kwargs.pop('password', None)
        self.connect_timeout = kwargs.pop('timeout', 10)
        self._client = kwargs.pop('client', None)
        if kwargs:
            extra_name = tuple(kwargs)[0]
            raise TypeError("__init__() got an unexpected keyword argument '%s'" % extra_name)

    def connect(self):
        return SMTPClient(self.hostname, self.port, timeout=self.connect_timeout)

    def send(self, fromaddr, toaddrs, message):
        msg_was_sent = False
        try:
            if self._client is None:
                connection = self.connect()
            else:
                self._client.connect()
                connection = self._client
            connection.ehlo()

            is_tls_supported = connection.has_extn('starttls')
            if is_tls_supported:
                connection.starttls()
                connection.ehlo()
            if (self.username is not None) and (self.password is not None):
                connection.login(self.username, self.password)

            connection.sendmail(fromaddr, toaddrs, message)
            msg_was_sent = True
            connection.quit()
        except (SMTPException, OSError):
            pass
        return msg_was_sent


class DebugMailer(object):
    def __init__(self, simulate_failed_sending=False, send_callback=None):
        self.simulate_failed_sending = simulate_failed_sending
        self.send_callback = send_callback
        self.sent_mails = []

    def send(self, fromaddr, toaddrs, message):
        was_sent = True
        if self.send_callback:
            was_sent = self.send_callback(fromaddr, toaddrs, message)
        if self.simulate_failed_sending:
            was_sent = False
        if was_sent:
            self.sent_mails.append((fromaddr, toaddrs, message))
        return was_sent

