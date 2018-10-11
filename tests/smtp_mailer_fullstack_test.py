# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from pymta.test_util import SMTPTestCase
from pythonic_testcase import *

from schwarz.mailqueue import SMTPMailer
from schwarz.mailqueue.compat import IS_PYTHON3


class SMTPMailerFullstackTest(SMTPTestCase):
    def test_can_send_message(self):
        mailer = SMTPMailer(self.hostname, port=self.listen_port)
        fromaddr = 'foo@site.example'
        message = b'Header: value\n\nbody\n'
        toaddrs = ('bar@site.example', 'baz@site.example',)
        msg_was_sent = mailer.send(fromaddr, toaddrs, message)

        assert_true(msg_was_sent)
        received_queue = self.get_received_messages()
        assert_equals(1, received_queue.qsize())
        received_message = received_queue.get(block=False)
        assert_equals(fromaddr, received_message.smtp_from)
        assert_equals(toaddrs, tuple(received_message.smtp_to))
        assert_none(received_message.username)
        # pymta converts this to a string automatically
        expected_message = message.decode('ASCII')
        # in Python 2 the received message lacks the final '\n' (an unknown reason)
        if not IS_PYTHON3:
            expected_message = expected_message.rstrip('\n')
        assert_equals(expected_message, received_message.msg_data)

