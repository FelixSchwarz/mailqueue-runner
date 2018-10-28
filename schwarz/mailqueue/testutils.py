# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO
from mailbox import Maildir
import os

from pymta import SMTPCommandParser
from pymta.test_util import BlackholeDeliverer

from .smtpclient import SMTPClient


__all__ = ['build_queued_msg', 'fake_smtp_client', 'inject_message', 'SocketMock']

def build_queued_msg(return_path=None, envelope_to=None, msg_bytes=None):
    if return_path is None:
        return_path = b'foo@site.example'
    if envelope_to is None:
        envelope_to = b'bar@site.example'
    if msg_bytes is None:
        msg_bytes = b'Header: somevalue\n\nMsgBody\n'
    msg = (
        b'Return-path: ' + return_path + b'\n'
        b'Envelope-to: ' + envelope_to + b'\n' + \
        msg_bytes
    )
    return BytesIO(msg)

def inject_message(path_maildir, msg_fp):
    msg_maildir_id = Maildir(path_maildir).add(msg_fp)
    msg_path = os.path.join(path_maildir, 'new', msg_maildir_id)
    return msg_path


# --- test helpers to simulate a SMTP server ----------------------------------
try:
    from unittest import mock
except ImportError:
    try:
        import mock
    except ImportError:
        # Python 2 without "mock" library installed
        # "stub_socket_creation()" will fail but at least users can import this
        # module/use other functionality
        mock = None


def stub_socket_creation(socket_mock):
    connect_override = socket_mock._overrides.get('connect', None)
    def mock_create_connection(host_port, timeout, source_address):
        if connect_override:
            return connect_override()
        return socket_mock

    socket_func = 'schwarz.mailqueue.lib.smtplib_py37.socket.create_connection'
    if mock is None:
        raise ValueError('Please install the "mock" library.')
    return mock.patch(socket_func, new=mock_create_connection)


def fake_smtp_client(socket_mock=None, policy=None, overrides=None, **client_args):
    if socket_mock is None:
        socket_mock = SocketMock(policy=policy, overrides=overrides)

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
    client.server = socket_mock
    return client


class FakeChannel(object):
    def __init__(self):
        self._ignore_write_operations = False
        self.server_responses = []

    def write(self, data_bytes):
        if self._ignore_write_operations:
            return
        self.server_responses.append(data_bytes)

    def close(self):
        pass

    def drain_responses(self):
        response = ''
        while len(self.server_responses) > 0:
            response += self.server_responses.pop(0)
        return response.encode('ASCII')


class SocketMock(object):
    def __init__(self, policy=None, overrides=None):
        self.command_parser = None
        self.deliverer = BlackholeDeliverer()
        self.channel = FakeChannel()
        self.policy = policy
        self.reply_data = None
        # This attribute is actually not used in the SocketMock itself but it
        # simplifies some test code where we need to store some information to
        # "override" default behaviors.
        # Instead of adding yet another "state" variable just keep it here.
        self._overrides = overrides or {}

    @property
    def received_messages(self):
        return self.deliverer.received_messages

    # --- "socket" API --------------------------------------------------------
    def makefile(self, *args):
        self.command_parser = SMTPCommandParser(
            self.channel,
            '127.0.0.1', 2525,
            self.deliverer,
            policy=self.policy
        )
        self.reply_data = BytesIO()
        return self

    def readline(self, size):
        self._drain_responses()
        return self.reply_data.readline(size)

    def sendall(self, data):
        if isinstance(data, bytes):
            data = data.decode('ASCII')
        self.command_parser.process_new_data(data)

    def close(self):
        pass

    def _drain_responses(self):
        reply_bytes = self.channel.drain_responses()
        previous_position = self.reply_data.tell()
        self.reply_data.seek(0, os.SEEK_END)
        self.reply_data.write(reply_bytes)
        self.reply_data.seek(previous_position, os.SEEK_SET)

