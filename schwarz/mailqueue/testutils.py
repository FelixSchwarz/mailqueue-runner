# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import logging
import os
from datetime import datetime as DateTime, timedelta as TimeDelta, timezone
from email.message import Message
from io import BytesIO
from unittest import mock

from pymta import SMTPCommandParser
from pymta.test_util import BlackholeDeliverer
from schwarz.log_utils import ForwardingLogger

from .maildir_utils import move_message
from .queue_runner import MaildirBackedMsg, enqueue_message
from .smtpclient import SMTPClient


__all__ = [
    'assert_did_log_message',
    'create_alias_file',
    'create_ini',
    'fake_smtp_client',
    'info_logger',
    'inject_example_message',
    'retrieve_sent_message',
    'SocketMock',
]

def almost_now(dt):
    return dt - DateTime.now(timezone.utc) < TimeDelta(seconds=1)

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

def get_capture_logger(log_capture, level):
    logger = logging.Logger('__dummy__')
    connect_to_log_capture(logger, log_capture)
    return ForwardingLogger(forward_to=logger, forward_minlevel=level)

def connect_to_log_capture(logger, log_capture):
    lc = log_capture
    name = logger.name
    # -------------------------------------------------------------------------
    # code copied (with small adaptations) from Simplistix/testfixtures (MIT)
    #    LogCapture.install() in testfixtures/logcapture.py (git 61683a80)
    lc.old['levels'][name] = logger.level
    lc.old['handlers'][name] = logger.handlers
    lc.old['disabled'][name] = logger.disabled
    lc.old['progagate'][name] = logger.propagate
    logger.setLevel(lc.level)
    logger.handlers = [lc]
    logger.disabled = False
    if lc.propagate is not None:
        logger.propagate = lc.propagate
    lc.instances.add(lc)
    # -------------------------------------------------------------------------

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

def retrieve_sent_message(mta):
    received_queue = mta.get_received_messages()
    assert received_queue.qsize() == 1
    smtp_msg = received_queue.get(block=False)
    return smtp_msg

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
    def __init__(self, policy=None, overrides=None, authenticator=None):
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
        self._authenticator = authenticator

    @property
    def received_messages(self):
        return self.deliverer.received_messages

    # --- "socket" API --------------------------------------------------------
    def makefile(self, *args):
        self.command_parser = SMTPCommandParser(
            self.channel,
            '127.0.0.1', 2525,
            self.deliverer,
            policy=self.policy,
            authenticator=self._authenticator,
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
