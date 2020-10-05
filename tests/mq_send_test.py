# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import email
import os
import re

from pymta.test_util import SMTPTestCase
from pythonic_testcase import *
from schwarz.fakefs_helpers import TempFS

from schwarz.mailqueue import create_maildir_directories
from schwarz.mailqueue.cli import send_test_message_main
# prevent nosetests from running this imported function as "test"
send_test_message_main.__test__ = False


class MQSendTest(SMTPTestCase):
    def setUp(self):
        super(MQSendTest, self).setUp()
        self.tempfs = TempFS.set_up(test=self)

    def test_can_send_test_message(self):
        config_path = self._create_ini()
        path_maildir = os.path.join(self.tempfs.root, 'mailqueue')
        create_maildir_directories(path_maildir)

        cmd = ['mq-send-test', config_path, path_maildir, '--quiet', '--from=bar@site.example', '--to=foo@site.example']
        rc = send_test_message_main(argv=cmd, return_rc_code=True)
        assert_equals(0, rc)

        received_queue = self.get_received_messages()
        assert_equals(1, received_queue.qsize())
        smtp_msg = received_queue.get(block=False)
        assert_equals('bar@site.example', smtp_msg.smtp_from)
        assert_equals(('foo@site.example',), tuple(smtp_msg.smtp_to))
        assert_none(smtp_msg.username)
        msg = email.message_from_string(smtp_msg.msg_data)
        assert_startswith('Test message', msg['Subject'])
        assert_matches('^<[^@>]+@mqrunner.example>$', msg['Message-ID'],
            message='test message should use custom Msg-ID domain (with correct brackets)')

    def _create_ini(self):
        config_str = '\n'.join([
            '[mqrunner]',
            'smtp_hostname = %s' % self.hostname,
            'smtp_port = %d' % self.listen_port,
        ])
        config_path = self.tempfs.create_file('config.ini', contents=config_str.encode('ascii'))
        return str(config_path.path)


def assert_startswith(substr, full_str):
    assert_true(full_str.startswith(substr))

def assert_matches(pattern, text_str, message=None):
    match = re.match(pattern, text_str)
    assert_not_none(match, message=message)

