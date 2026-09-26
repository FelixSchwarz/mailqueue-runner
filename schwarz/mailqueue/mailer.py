# SPDX-License-Identifier: MIT

from __future__ import annotations

from enum import Enum
from io import BytesIO

from .message_utils import MsgInfo, SendResult
from .smtpclient import SMTPClient, SMTPException


__all__ = ['DebugMailer', 'SMTPMailer', 'TLSMode', 'required_tls_mode']

# Port 465 is reserved for implicit TLS (RFC 8314) so we never send anything in
# plain text there.
SMTPS_PORT = 465

class TLSMode(Enum):
    # TLS right after connecting (SMTPS, usually port 465)
    IMPLICIT = 'implicit'
    # upgrade to TLS via "STARTTLS", do not send the message if the server does
    # not support it
    STARTTLS = 'starttls'
    # upgrade to TLS via "STARTTLS" if the server supports it, otherwise send the
    # message (and credentials) in plain text
    OPPORTUNISTIC = 'opportunistic'


def required_tls_mode(port: int) -> TLSMode:
    """Return the TLS mode which always encrypts the connection to the given
    port (without falling back to plain text)."""
    return TLSMode.IMPLICIT if (port == SMTPS_PORT) else TLSMode.STARTTLS


class SMTPMailer:
    def __init__(self, hostname: str | None = None, **kwargs):
        if (hostname is None) and ('client' not in kwargs):
            raise TypeError('not enough parameters for __init__(): please specify at least "hostname" or "client"')  # noqa: E501 (line too long)
        self.hostname = hostname
        self.port = int(kwargs.pop('port', 25))
        is_smtps_port = (self.port == SMTPS_PORT)
        tls = kwargs.pop('tls', None)
        if tls is None:
            tls = TLSMode.IMPLICIT if is_smtps_port else TLSMode.OPPORTUNISTIC
        self.tls = TLSMode(tls)
        if is_smtps_port and (self.tls != TLSMode.IMPLICIT):
            raise ValueError('port %d requires implicit TLS (tls=%r)' % (SMTPS_PORT, self.tls.value))
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
            implicit_tls=(self.tls == TLSMode.IMPLICIT),
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

            supports_starttls = connection.has_extn('starttls')
            if (self.tls == TLSMode.STARTTLS) and not supports_starttls:
                connection.quit()
                raise SMTPException('TLS required but the server does not support STARTTLS')
            use_starttls = (self.tls != TLSMode.IMPLICIT) and supports_starttls
            if use_starttls:
                connection.starttls()
                connection.ehlo()
            if (self.username is not None) and (self.password is not None):
                connection.login(self.username, self.password)

            connection.sendmail(fromaddr, toaddrs, message)
            msg_was_sent.value = True
            connection.quit()
        except (SMTPException, OSError) as e:
            if self.smtp_log:
                log_msg = '%s (%s)' % (str(e), e.__class__.__name__)
                self.smtp_log.warning(log_msg)
        return msg_was_sent


class DebugMailer:
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
