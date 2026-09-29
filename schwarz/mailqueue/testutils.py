# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import logging
import os
import queue
import socket
import threading
from dataclasses import dataclass
from datetime import datetime as DateTime, timedelta as TimeDelta, timezone
from email.message import Message
from typing import Any
from unittest import mock

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, AuthResult
from schwarz.log_utils import ForwardingLogger

from .maildir_utils import move_message
from .queue_runner import MaildirBackedMsg, enqueue_message
from .smtpclient import SMTPClient


__all__ = [
    'accept_any_login',
    'assert_did_log_message',
    'create_alias_file',
    'create_ini',
    'fake_smtp_client',
    'FakeSSLContext',
    'info_logger',
    'inject_example_message',
    'MessageCollector',
    'ReceivedMessage',
    'retrieve_sent_message',
    'SMTPTestServer',
    'SocketMock',
]

def almost_now(tolerance: TimeDelta = TimeDelta(seconds=2)):
    now = DateTime.now(timezone.utc)
    pytest_version = tuple(int(part) for part in pytest.__version__.split('.')[:2])
    if pytest_version >= (9, 1):
        return pytest.approx(now, abs=tolerance)
    # pytest < 9.1 (e.g. on Python 3.9) compares datetimes strictly in `approx()`
    return _ApproxDateTime(now, tolerance)


class _ApproxDateTime:
    def __init__(self, expected: DateTime, tolerance: TimeDelta):
        self.expected = expected
        self.tolerance = tolerance

    def __eq__(self, actual) -> bool:
        return abs(actual - self.expected) <= self.tolerance

    def __repr__(self) -> str:
        return f'{self.expected} ± {self.tolerance}'


def message():
    msg = Message()
    msg['Header'] = 'somevalue'
    msg.set_payload('MsgBody')
    return msg

def inject_example_message(queue_path, sender=b'foo@site.example', recipient=None,
                           recipients=None, msg_bytes=None, target_folder='new',
                           queue_date=None):
    if msg_bytes is None:
        msg_bytes = message()
    if recipient and recipients:
        raise ValueError('inject_example_message() got conflicting parameters: recipient=%r, recipients=%r' % (recipient, recipients))  # noqa: E501 (line too long)
    if (recipient is None) and (recipients is None):
        recipients = (b'bar@site.example',)
    elif recipient:
        recipients = (recipient,)
    msg_path = enqueue_message(msg_bytes, queue_path, sender, recipients, queue_date=queue_date)
    if target_folder != 'new':
        msg_path = move_message(msg_path, target_folder=target_folder, open_file=False)
    return MaildirBackedMsg(msg_path)

def create_ini(hostname, port, dir_path, *, queue_dir=None,
               from_='testuser@host.example', log_dir=None):
    config_str = '\n'.join([
        '[mqrunner]',
        'smtp_hostname = %s' % hostname,
        'smtp_port = %d' % port,
    ])
    if queue_dir:
        config_str += f'\nqueue_dir = {queue_dir}'
    if from_:
        config_str += f'\nfrom = {from_}'
    if log_dir:
        delivery_log = str(log_dir / 'mq_delivery.log')
        config_str += f'\ndelivery_log = {delivery_log}'
        queue_log = str(log_dir / 'mq_queue.log')
        config_str += f'\nqueue_log = {queue_log}'
    if not dir_path:
        return config_str
    config_path = os.path.join(dir_path, 'config.ini')
    with open(config_path, 'wb') as config_fp:
        config_fp.write(config_str.encode('ascii'))
    return config_path


def create_alias_file(aliases, dir_path) -> str:
    aliases_contents = ''
    for alias, target in aliases.items():
        aliases_contents += f'{alias}: {target}\n'

    aliases_path = dir_path / 'aliases'
    aliases_path.write_text(aliases_contents)
    return str(aliases_path)


# --- helpers to capture/check logged messages --------------------------------
def info_logger(log_capture):
    return get_capture_logger(log_capture, level=logging.INFO)

def get_capture_logger(log_capture, level: int) -> ForwardingLogger:
    """
    Return a logger which forwards all messages (>= `level`) to the given
    log capture.

    `log_capture` can be pytest's `caplog` fixture or any `logging.Handler`
    which stores the log records in a `.records` attribute.
    """
    logger = logging.Logger('__dummy__')
    # pytest's "caplog" fixture is not a handler itself
    handler = getattr(log_capture, 'handler', log_capture)
    logger.handlers = [handler]
    logger.disabled = False
    return ForwardingLogger(forward_to=logger, forward_minlevel=level)

def assert_did_log_message(log_capture, expected_msg):
    lc = log_capture
    if not lc.records:
        raise AssertionError('no messages logged')

    log_messages = [log_record.msg for log_record in lc.records]
    if expected_msg in log_messages:
        return
    error_msg = 'message not logged: "%s" - did log %s' % (expected_msg, log_messages)
    raise AssertionError(error_msg)


# --- test helpers to simulate a SMTP server ----------------------------------

@dataclass
class ReceivedMessage:
    smtp_from: str
    smtp_to: tuple[str, ...]
    # message as transmitted in the DATA command (CRLF line endings, without
    # the final "." line)
    msg_bytes: bytes
    username: str | None = None


class MessageCollector:
    """
    aiosmtpd handler which stores all received messages in `received_messages`.

    Subclasses can override aiosmtpd's `handle_*()` hooks to reject senders or
    recipients.
    """
    def __init__(self):
        self.received_messages: queue.Queue[ReceivedMessage] = queue.Queue()

    async def handle_DATA(self, server, session, envelope) -> str:
        login = getattr(session.auth_data, 'login', None)
        received_msg = ReceivedMessage(
            smtp_from = envelope.mail_from,
            smtp_to   = tuple(envelope.rcpt_tos),
            msg_bytes = envelope.original_content,
            username  = login.decode('utf-8') if login else None,
        )
        self.received_messages.put(received_msg)
        return '250 OK'


def accept_any_login(server, session, envelope, mechanism, auth_data) -> AuthResult:
    """aiosmtpd authenticator which accepts all credentials"""
    return AuthResult(success=True, auth_data=auth_data)


def _smtp_server_args(server_args: dict[str, Any]) -> dict[str, Any]:
    server_args = dict(server_args)
    # fixed host name: predictable server responses (and no DNS lookup)
    server_args.setdefault('hostname', 'mx.site.example')
    server_args.setdefault('ident', 'ESMTP')
    if server_args.get('authenticator'):
        # tests use plain-text connections
        server_args.setdefault('auth_require_tls', False)
    return server_args


class SMTPTestServer(Controller):
    """
    SMTP server (listening on a random port on 127.0.0.1) which runs in a
    background thread. Received messages are available via
    `.received_messages`.
    """
    def __init__(self, handler: MessageCollector | None = None, **server_args):
        if handler is None:
            handler = MessageCollector()
        server_args = _smtp_server_args(server_args)
        # Controller uses "hostname" for the listen address
        server_hostname = server_args.pop('hostname')
        super().__init__(
            handler,
            hostname        = '127.0.0.1',
            port            = 0,
            server_hostname = server_hostname,
            **server_args,
        )

    def _trigger_server(self):
        # "port=0" tells the OS to pick a free port. The Controller needs to
        # know the actual port as it connects to the server to check that the
        # server is running.
        assert isinstance(self.server, asyncio.Server)
        self.port = self.server.sockets[0].getsockname()[1]
        super()._trigger_server()

    @property
    def received_messages(self) -> queue.Queue[ReceivedMessage]:
        return self.handler.received_messages


def retrieve_sent_message(mta) -> ReceivedMessage:
    received_queue = mta.received_messages
    assert received_queue.qsize() == 1
    smtp_msg = received_queue.get(block=False)
    return smtp_msg

def stub_socket_creation(socket_mock):
    connect_override = socket_mock._overrides.get('connect', None)
    def mock_create_connection(host_port, timeout, source_address):
        if connect_override:
            return connect_override()
        socket_mock.open_connection()
        return socket_mock

    socket_func = 'schwarz.mailqueue.smtpclient.socket.create_connection'
    if mock is None:
        raise ValueError('Please install the "mock" library.')
    return mock.patch(socket_func, new=mock_create_connection)


def fake_smtp_client(socket_mock=None, handler=None, overrides=None, **client_args):
    if socket_mock is None:
        socket_mock = SocketMock(handler=handler, overrides=overrides)

    hostname = 'site.invalid'
    has_connect_override = ('connect' in socket_mock._overrides)
    remote_host = hostname if not has_connect_override else ''
    with stub_socket_creation(socket_mock):
        # by default SMTPClient tries to open a connection in "__init__()" when
        # the "host" parameter is specified.
        # If the test tries to override "connect" we delay the connection:
        # Some tests might want to simulate exceptions during ".connect()" and
        # it is much nicer if these exceptions are raised later (even though
        # the caller must stub out the "socket.create_connection()" function
        # again).
        client = SMTPClient(host=remote_host, port=123, **client_args)
    if has_connect_override:
        client._host = hostname
    client.server = socket_mock  # ty: ignore[unresolved-attribute]
    return client


class FakeSSLContext:
    def __init__(self):
        self.wrapped = []

    def wrap_socket(self, sock, server_hostname=None):
        # "makefile()" was not called yet -> no data was read from the socket
        is_pristine = (getattr(sock, 'reader', None) is None)
        self.wrapped.append((sock, server_hostname, is_pristine))
        return sock


_background_loop: asyncio.AbstractEventLoop | None = None
_background_loop_lock = threading.Lock()

def _get_background_loop() -> asyncio.AbstractEventLoop:
    global _background_loop
    with _background_loop_lock:
        if _background_loop is None:
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, name='SocketMock', daemon=True)
            thread.start()
            _background_loop = loop
    return _background_loop


class SocketMock:
    """
    Socket which is connected to an in-process aiosmtpd server without using
    the network: The server side of a `socket.socketpair()` is handled by an
    event loop in a background thread.
    """
    def __init__(self, handler: MessageCollector | None = None, overrides=None, **server_args):
        self.handler = handler if (handler is not None) else MessageCollector()
        self._server_args = _smtp_server_args(server_args)
        self.sock: socket.socket | None = None
        self.reader = None
        # This attribute is actually not used in the SocketMock itself but it
        # simplifies some test code where we need to store some information to
        # "override" default behaviors.
        # Instead of adding yet another "state" variable just keep it here.
        self._overrides = overrides or {}

    @property
    def received_messages(self) -> queue.Queue[ReceivedMessage]:
        return self.handler.received_messages

    def open_connection(self) -> None:
        client_sock, server_sock = socket.socketpair()
        # tests should fail instead of hanging forever if the server does not respond
        client_sock.settimeout(10)
        loop = _get_background_loop()
        protocol_factory = lambda: SMTP(self.handler, loop=loop, **self._server_args)
        connect = loop.connect_accepted_socket(protocol_factory, server_sock)
        asyncio.run_coroutine_threadsafe(connect, loop).result(timeout=10)
        self.sock = client_sock
        self.reader = None

    # --- "socket" API --------------------------------------------------------
    def makefile(self, *args, **kwargs):
        self.reader = self._connected_socket().makefile(*args, **kwargs)
        return self.reader

    def sendall(self, data: bytes) -> None:
        self._connected_socket().sendall(data)

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()

    def _connected_socket(self) -> socket.socket:
        if self.sock is None:
            raise RuntimeError('socket is not connected')
        return self.sock
