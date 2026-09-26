# SPDX-License-Identifier: MIT

from __future__ import annotations

import base64
import logging
import re
import socket
import ssl
from collections.abc import Iterable

from smtpproto.protocol import (
    ClientState,
    SMTPClientProtocol,
    SMTPException,
    SMTPProtocolViolation,
    SMTPResponse,
)


__all__ = [
    'SMTPClient',
    'SMTPException',
    'SMTPRecipientRefused',
    'SMTPResponseError',
    'SMTPSenderRefused',
    'SMTPServerDisconnected',
    'create_ssl_context',
]

CRLF = '\r\n'
bCRLF = b'\r\n'
# RFC 5321 limits the reply line length to 512 bytes but some servers send
# longer lines. Use the same limit as Python's smtplib.
_MAXLINE = 8192

# "socket.create_connection()" uses a private sentinel to distinguish "no
# timeout specified" (use "socket.getdefaulttimeout()") from an explicit "None"
# (block forever). typeshed does not declare that sentinel and stubs the
# parameter as "float | None", so we do the same.
_GLOBAL_DEFAULT_TIMEOUT: float | None = socket._GLOBAL_DEFAULT_TIMEOUT  # ty: ignore[unresolved-attribute]


class SMTPServerDisconnected(SMTPException):
    pass


class SMTPResponseError(SMTPException):
    def __init__(self, code: int, msg: str):
        self.smtp_code = code
        self.smtp_error = msg
        super().__init__(code, msg)

    def __str__(self):
        return '%d %s' % (self.smtp_code, self.smtp_error)


class SMTPSenderRefused(SMTPResponseError):
    def __init__(self, code: int, msg: str, sender: str):
        super().__init__(code, msg)
        self.sender = sender
        self.args = (code, msg, sender)

    def __str__(self):
        return '%d %s (sender: %s)' % (self.smtp_code, self.smtp_error, self.sender)


class SMTPRecipientRefused(SMTPResponseError):
    def __init__(self, code: int, msg: str, recipient: str):
        super().__init__(code, msg)
        self.recipient = recipient
        self.args = (code, msg, recipient)

    def __str__(self):
        return '%d %s (recipient: %s)' % (self.smtp_code, self.smtp_error, self.recipient)


class _SMTPProtocol(SMTPClientProtocol):
    def raw_data(self, msg: bytes) -> None:
        # smtpproto's ".data()" only accepts "EmailMessage" instances which
        # are serialized again. We must not re-serialize the queued message
        # (e.g. to keep DKIM signatures intact) so we need to access some
        # internal attributes here.
        self._require_state(ClientState.send_data)
        # SMTP requires CRLF line endings. Also normalizing bare CR/LF prevents
        # "SMTP smuggling" (e.g. CVE-2023-51764, CVE-2023-51766): Otherwise
        # sequences like "\n.\r\n" in the message might be interpreted as
        # "end of data" by some servers. Also, many servers reject messages
        # with bare LF nowadays.
        data = _fix_eols(msg)
        data = re.sub(br'(?m)^\.', b'..', data)
        if not data.endswith(bCRLF):
            data += bCRLF
        self._out_buffer += data + b'.' + bCRLF
        self._state = ClientState.data_sent


class SMTPClient:
    """
    Blocking SMTP client built on top of smtpproto's sans-io state machine.

    We do not use smtpproto's own (anyio-based) clients because
    - we want to log the complete SMTP dialog (line by line, as it happens) and
    - we don't want to deliver a message if *any* recipient was refused
      (Python's smtplib as well as smtpproto's high-level client handle that
      differently).
    """

    def __init__(
            self,
            host: str | None = None,
            port: int = 0,
            local_hostname: str | None = None,
            timeout: float | None = _GLOBAL_DEFAULT_TIMEOUT,
            source_address: tuple[str, int] | None = None,
            smtp_log: logging.Logger | None = None,
            implicit_tls: bool = False,
            ssl_context: ssl.SSLContext | None = None,
    ):
        self._host = host
        self._port = port
        self.local_hostname = local_hostname or socket.getfqdn()
        self.timeout = timeout
        self.source_address = source_address
        self.smtp_log = smtp_log
        # "implicit TLS" (RFC 8314, usually port 465): TLS handshake right
        # after the TCP connection was established (instead of "STARTTLS")
        self.implicit_tls = implicit_tls
        self.ssl_context = ssl_context
        self.sock = None
        self._file = None
        self.protocol = _SMTPProtocol()
        if host:
            self.connect(host, port)

    def connect(self, host: str | None = None, port: int | None = None) -> SMTPResponse:
        if host:
            self._host = host
        if port:
            self._port = port
        host = self._host
        if not host:
            raise ValueError('no SMTP host specified')
        port = self._port or 25
        self._log_connect(host, port)
        sock = socket.create_connection((host, port), self.timeout, self.source_address)
        self.sock = self._wrap_socket(sock) if self.implicit_tls else sock
        self._file = self.sock.makefile('rb')
        self.protocol = _SMTPProtocol()
        response = self._read_response()
        if response.is_error():
            self.close()
            raise SMTPResponseError(response.code, response.message)
        return response

    def ehlo(self, name: str | None = None) -> SMTPResponse:
        # smtpproto automatically falls back to "HELO" if the server does
        # not understand "EHLO".
        response = self._command(self.protocol.send_greeting, name or self.local_hostname)
        if response.is_error():
            raise SMTPResponseError(response.code, response.message)
        return response

    def has_extn(self, name: str) -> bool:
        return name.upper() in self.protocol.extensions

    def starttls(self, context: ssl.SSLContext | None = None) -> SMTPResponse:
        self._ehlo_if_needed()
        response = self._command(self.protocol.start_tls)
        if self.sock is None:
            raise SMTPServerDisconnected('please run connect() first')
        self.sock = self._wrap_socket(self.sock, context)
        self._file = self.sock.makefile('rb')
        return response

    def login(self, user: str, password: str) -> SMTPResponse:
        self._ehlo_if_needed()
        mechanisms = self.protocol.auth_mechanisms
        _b64 = lambda s: base64.b64encode(s.encode('utf-8')).decode('ascii')
        if 'PLAIN' in mechanisms:
            secret = _b64('\0%s\0%s' % (user, password))
            response = self._command(self.protocol.authenticate, 'PLAIN', secret)
        elif 'LOGIN' in mechanisms:
            response = self._command(self.protocol.authenticate, 'LOGIN')
            for value in (user, password):
                if response.code != 334:
                    break
                response = self._command(self.protocol.send_authentication_data, _b64(value))
        else:
            raise SMTPException('No suitable authentication method found.')

        if response.code != 235:
            raise SMTPResponseError(response.code, response.message)
        return response

    def sendmail(self, from_addr: str, to_addrs: str | Iterable[str],
                 msg: bytes | str) -> SMTPResponse:
        self._ehlo_if_needed()
        if isinstance(msg, str):
            msg = msg.encode('ascii')
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]

        response = self._command(self.protocol.mail, from_addr)
        if response.is_error():
            self._rset()
            raise SMTPSenderRefused(response.code, response.message, from_addr)
        # Python's smtplib only raises an exception if *all* recipients were refused.
        # However we want to be able to retry delivery for the complete message without
        # sending duplicate messages.
        for recipient in to_addrs:
            response = self._command(self.protocol.recipient, recipient)
            if response.is_error():
                self._rset()
                raise SMTPRecipientRefused(response.code, response.message, recipient)
        response = self._command(self.protocol.start_data)
        if response.is_error():
            self._rset()
            raise SMTPResponseError(response.code, response.message)
        response = self._command(self.protocol.raw_data, msg)
        if response.is_error():
            raise SMTPResponseError(response.code, response.message)
        return response

    def quit(self) -> SMTPResponse | None:
        response = None
        if (self.sock is not None) and (self.protocol.state is not ClientState.finished):
            response = self._command(self.protocol.quit)
        self.close()
        return response

    def close(self) -> None:
        file_, sock = self._file, self.sock
        self._file = None
        self.sock = None
        try:
            if file_ is not None:
                file_.close()
        finally:
            if sock is not None:
                sock.close()

    # --- internal helpers ----------------------------------------------------
    def _wrap_socket(self, sock: socket.socket, context: ssl.SSLContext | None = None) -> ssl.SSLSocket:
        context = context or self.ssl_context
        if context is None:
            context = create_ssl_context()
        return context.wrap_socket(sock, server_hostname=self._host)

    def _ehlo_if_needed(self) -> None:
        if self.protocol.state is ClientState.greeting_received:
            self.ehlo()

    def _rset(self) -> None:
        resettable_states = (ClientState.mailtx, ClientState.recipient_sent, ClientState.send_data)
        if self.protocol.state not in resettable_states:
            return
        try:
            self._command(self.protocol.reset)
        except (SMTPException, OSError):
            # The caller will raise a more specific exception anyway.
            pass

    def _command(self, command, *args) -> SMTPResponse:
        if self.sock is None:
            raise SMTPServerDisconnected('please run connect() first')
        command(*args)
        self._flush()
        return self._read_response()

    def _flush(self) -> None:
        data = self.protocol.get_outgoing_data()
        if not data:
            return
        if self.sock is None:
            raise SMTPServerDisconnected('please run connect() first')
        self._log_sent_data(data)
        self.sock.sendall(data)

    def _read_response(self) -> SMTPResponse:
        if self._file is None:
            raise SMTPServerDisconnected('please run connect() first')
        while True:
            line = self._file.readline(_MAXLINE + 1)
            if not line:
                self.close()
                raise SMTPServerDisconnected('Connection unexpectedly closed')
            if len(line) > _MAXLINE:
                self.close()
                raise SMTPProtocolViolation('Line too long.')
            if self.smtp_log:
                self.smtp_log.debug('<= %s', _to_str(line.rstrip(bCRLF)))
            try:
                response = self.protocol.feed_bytes(line)
            except SMTPProtocolViolation:
                # e.g. "421" (service not available) at any point in the dialog
                self.close()
                raise
            if response is not None:
                return response
            # smtpproto might need to send a command on its own
            # (e.g. "HELO" if the server rejected "EHLO").
            self._flush()

    def _log_connect(self, host: str, port: int) -> None:
        if not self.smtp_log:
            return
        log_tmpl = 'connecting to %(host)s:%(port)s'
        optional = []
        if self.implicit_tls:
            optional.append('implicit TLS')
        if self.timeout not in (None, _GLOBAL_DEFAULT_TIMEOUT):
            float_to_str = lambda f: ('%.4f' % f).rstrip('0').rstrip('.')
            optional.append('timeout=%ss' % float_to_str(self.timeout))
        if self.source_address:
            source_host, source_port = self.source_address
            shost_str = source_host or '<default>'
            sport_str = source_port or '<default>'
            optional.append('source address=%s:%s' % (shost_str, sport_str))
        if optional:
            log_tmpl += ' (%s)' % (', '.join(optional))
        self.smtp_log.debug(log_tmpl, {'host': host, 'port': port})

    def _log_sent_data(self, data: bytes) -> None:
        if not self.smtp_log:
            return
        for line in re.split(b'\r?\n', data.rstrip(bCRLF)):
            self.smtp_log.debug('=> %s', _to_str(line))


def create_ssl_context(verify: bool = True) -> ssl.SSLContext:
    """Return an SSL context for SMTP connections.

    By default the server certificate (and hostname) is verified against the
    system's CA certificates. "verify=False" disables all checks (e.g. for
    internal mail relays with self-signed certificates) so the connection is
    only protected against passive eavesdropping."""
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _fix_eols(data: bytes) -> bytes:
    return re.sub(br'(?:\r\n|\n|\r(?!\n))', bCRLF, data)


def _to_str(line: bytes) -> str:
    # The log should show exactly what was sent/received without failing on
    # non-ASCII bytes.
    return line.decode('ascii', errors='backslashreplace')
