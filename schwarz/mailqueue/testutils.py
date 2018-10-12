# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO
from mailbox import Maildir
import os

from pymta import SMTPCommandParser
from pymta.test_util import BlackholeDeliverer

from .smtpclient import SMTPClient


__all__ = ['build_queued_msg', 'inject_message', 'FakeSMTP']

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


class FakeSMTP(SMTPClient):
    def __init__(self, *args, **kwargs):
        super(FakeSMTP, self).__init__(*args, **kwargs)
        self.deliverer = BlackholeDeliverer()
        self.channel = FakeChannel()
        self.command_parser = SMTPCommandParser(self.channel, '127.0.0.1', 2525, self.deliverer)
        self._consume_initial_greeting()

    @property
    def received_messages(self):
        return self.deliverer.received_messages

    def _consume_initial_greeting(self):
        self.getreply()

    def send(self, s):
        if isinstance(s, bytes):
            s = s.decode('ASCII')
        self.command_parser.process_new_data(s)

    def getreply(self):
        reply_bytes = self.channel.drain_responses()
        self.file = BytesIO(reply_bytes)
        reply = super(FakeSMTP, self).getreply()
        self.file = None
        return reply

    def close(self):
        self.channel.drain_responses()
