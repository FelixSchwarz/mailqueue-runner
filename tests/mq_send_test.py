# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import email
import re
import shutil
import tempfile

from pymta.test_util import SMTPTestCase

from schwarz.mailqueue.cli import send_test_message_main
from schwarz.mailqueue.testutils import create_ini
# prevent nosetests from running this imported function as "test"
send_test_message_main.__test__ = False


class MQSendTest(SMTPTestCase):
    def setUp(self):
        super(MQSendTest, self).setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        super(MQSendTest, self).tearDown()

    def test_can_send_test_message(self):
        config_path = create_ini(self.hostname, self.listen_port, dir_path=self.tmpdir)

        cmd = ['mq-send-test', config_path, '--quiet', '--from=bar@site.example', '--to=foo@site.example']
        rc = send_test_message_main(argv=cmd, return_rc_code=True)
        assert rc == 0

        received_queue = self.get_received_messages()
        assert received_queue.qsize() == 1
        smtp_msg = received_queue.get(block=False)
        assert smtp_msg.smtp_from == 'bar@site.example'
        assert tuple(smtp_msg.smtp_to) == ('foo@site.example',)
        assert smtp_msg.username is None
        msg = email.message_from_string(smtp_msg.msg_data)
        assert_startswith('Test message', msg['Subject'])
        assert_matches('^<[^@>]+@mqrunner.example>$', msg['Message-ID'],
            message='test message should use custom Msg-ID domain (with correct brackets)')



def assert_startswith(substr, full_str):
    assert full_str.startswith(substr)

def assert_matches(pattern, text_str, message=None):
    match = re.match(pattern, text_str)
    assert match is not None, message

