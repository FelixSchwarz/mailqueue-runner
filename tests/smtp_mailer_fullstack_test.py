# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from pymta.test_util import SMTPTestCase
from pythonic_testcase import *

from schwarz.mailqueue import SMTPMailer


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
        sent_message = received_queue.get(block=False)
        assert_equals(fromaddr, sent_message.smtp_from)
        assert_equals(toaddrs, tuple(sent_message.smtp_to))
        assert_none(sent_message.username)
        # pymta converts this to a string automatically
        assert_equals('Header: value\n\nbody', sent_message.msg_data)

