# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO
from smtplib import SMTPException
import socket

from .message_utils import MsgInfo, SendResult
from .smtpclient import SMTPClient


__all__ = ['DebugMailer', 'SMTPMailer']

class SMTPMailer(object):
    def __init__(self, hostname=None, **kwargs):
        if (hostname is None) and ('client' not in kwargs):
            raise TypeError('not enough parameters for __init__(): please specify at least "hostname" or "client"')
        self.hostname = hostname
        # ensure "port" is numeric as "socket.connect()" in Python 2 only
        # accepts ints (in Python 3 '25' works as well).
        self.port = int(kwargs.pop('port', 25))
        self.username = kwargs.pop('username', None)
        self.password = kwargs.pop('password', None)
        self.connect_timeout = kwargs.pop('timeout', 10)
        self.smtp_log = kwargs.pop('smtp_log', None)
        self._client = kwargs.pop('client', None)
        if kwargs:
            extra_name = tuple(kwargs)[0]
            raise TypeError("__init__() got an unexpected keyword argument '%s'" % extra_name)

    def init_smtp_client(self):
        smtp_client = SMTPClient(self.hostname, self.port, timeout=self.connect_timeout, smtp_log=self.smtp_log)
        return smtp_client

    def send(self, fromaddr, toaddrs, message):
        msg_was_sent = SendResult(False, queued=False, transport='smtp')
        try:
            if self._client is None:
                connection = self.init_smtp_client()
            else:
                client = self._client
                is_connected = (getattr(client, 'sock', None) is not None)
                if not is_connected:
                    client.connect()
                connection = client
            connection.ehlo()

            is_tls_supported = connection.has_extn('starttls')
            if is_tls_supported:
                connection.starttls()
                connection.ehlo()
            if (self.username is not None) and (self.password is not None):
                connection.login(self.username, self.password)

            connection.sendmail(fromaddr, toaddrs, message)
            msg_was_sent.value = True
            connection.quit()
        except (SMTPException, OSError, socket.error) as e:
            if self.smtp_log:
                log_msg = '%s (%s)' % (str(e), e.__class__.__name__)
                self.smtp_log.warn(log_msg)
        return msg_was_sent


class DebugMailer(object):
    def __init__(self, simulate_failed_sending=False, send_callback=None):
        self.simulate_failed_sending = simulate_failed_sending
        self.send_callback = send_callback
        self.sent_mails = []

    def send(self, fromaddr, toaddrs, message):
        was_sent = SendResult(True, queued=False, transport='debug')
        if self.send_callback:
            was_sent = self.send_callback(fromaddr, toaddrs, message)
        if self.simulate_failed_sending:
            was_sent.value = False
        if was_sent:
            msg_info = MsgInfo(fromaddr, toaddrs, BytesIO(message))
            self.sent_mails.append(msg_info)
        return was_sent

