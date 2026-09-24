# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import socket
from io import BytesIO

from .message_utils import MsgInfo, SendResult
from .smtpclient import SMTPClient, SMTPException


__all__ = ['DebugMailer', 'SMTPMailer']

class SMTPMailer(object):
    def __init__(self, hostname=None, **kwargs):
        if (hostname is None) and ('client' not in kwargs):
            raise TypeError('not enough parameters for __init__(): please specify at least "hostname" or "client"')  # noqa: E501 (line too long)
        self.hostname = hostname
        self.port = int(kwargs.pop('port', 25))
        # "implicit": TLS right after connecting (SMTPS, usually port 465)
        # "starttls": upgrade to TLS via "STARTTLS" if the server supports it
        # Port 465 is reserved for implicit TLS (RFC 8314) so we never send
        # anything in plain text there.
        is_smtps_port = (self.port == 465)
        default_tls = 'implicit' if is_smtps_port else 'starttls'
        self.tls = kwargs.pop('tls', None) or default_tls
        if self.tls not in ('implicit', 'starttls'):
            raise ValueError('invalid value for "tls": %r (expected "implicit" or "starttls")' % self.tls)  # noqa: E501 (line too long)
        if is_smtps_port and (self.tls != 'implicit'):
            raise ValueError('port 465 requires implicit TLS (tls=%r)' % self.tls)
        self.username = kwargs.pop('username', None)
        self.password = kwargs.pop('password', None)
        self.connect_timeout = kwargs.pop('timeout', 10)
        self.smtp_log = kwargs.pop('smtp_log', None)
        self._client = kwargs.pop('client', None)
        if kwargs:
            extra_name = tuple(kwargs)[0]
            raise TypeError("__init__() got an unexpected keyword argument '%s'" % extra_name)

    def init_smtp_client(self):
        smtp_client = SMTPClient(
            self.hostname,
            self.port,
            timeout=self.connect_timeout,
            smtp_log=self.smtp_log,
            implicit_tls=(self.tls == 'implicit'),
        )
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

            use_starttls = (self.tls == 'starttls') and connection.has_extn('starttls')
            if use_starttls:
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
                self.smtp_log.warning(log_msg)
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
