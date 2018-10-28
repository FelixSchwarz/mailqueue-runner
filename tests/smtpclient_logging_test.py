# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import logging
import socket

from pythonic_testcase import *
from testfixtures import LogCapture

from schwarz.mailqueue.testutils import fake_smtp_client



class SMTPClientLoggingTest(PythonicTestCase):
    def test_can_log_connect(self):
        with LogCapture() as l:
            smtp_log = logging.getLogger('s')
            client = fake_smtp_client(smtp_log=smtp_log)
        assert_not_equals(0, len(l.records), message='no records logged')
        l.check(
            ('s', 'DEBUG', 'connecting to site.invalid:123')
        )

    def test_can_log_client_command(self):
        with LogCapture() as l:
            smtp_log = logging.getLogger('s')
            client = fake_smtp_client(smtp_log=smtp_log)
            client.ehlo('client.example')
            client.quit()
        assert_not_equals(0, len(l.records), message='no records logged')
        # pymta shortcoming: unable to set the server host name manually
        server_name = socket.getfqdn()
        l.check(
            ('s', 'DEBUG', 'connecting to site.invalid:123'),
            ('s', 'DEBUG', '=> ehlo client.example'),
            ('s', 'DEBUG', '<= 250-%s' % server_name),
            ('s', 'DEBUG', '<= 250 HELP'),
            ('s', 'DEBUG', '=> quit'),
            ('s', 'DEBUG', '<= 221 %s closing connection' % server_name),
        )

    def test_can_log_complete_smtp_interaction(self):
        from_ = 'sender@site.example'
        to_ = 'recipient@site.example'
        msg = b'Header: value\n\nbody'
        with LogCapture() as l:
            smtp_log = logging.getLogger('s')
            client = fake_smtp_client(smtp_log=smtp_log, local_hostname='client.example')
            client.sendmail(from_, to_, msg)
            client.quit()
        assert_not_equals(0, len(l.records), message='no records logged')
        # pymta shortcoming: unable to set the server host name manually
        server_name = socket.getfqdn()
        l.check(
            ('s', 'DEBUG', 'connecting to site.invalid:123'),
            ('s', 'DEBUG', '=> ehlo client.example'),
            ('s', 'DEBUG', '<= 250-%s' % server_name),
            ('s', 'DEBUG', '<= 250 HELP'),
            ('s', 'DEBUG', '=> mail FROM:<%s>' % from_),
            ('s', 'DEBUG', '<= 250 OK'),
            ('s', 'DEBUG', '=> rcpt TO:<%s>' % to_),
            ('s', 'DEBUG', '<= 250 OK'),
            ('s', 'DEBUG', '=> data'),
            ('s', 'DEBUG', '<= 354 Enter message, ending with "." on a line by itself'),

            ('s', 'DEBUG', '=> Header: value'),
            ('s', 'DEBUG', '=> '),
            ('s', 'DEBUG', '=> body'),
            ('s', 'DEBUG', '=> .'),

            ('s', 'DEBUG', '<= 250 OK'),
            ('s', 'DEBUG', '=> quit'),
            ('s', 'DEBUG', '<= 221 %s closing connection' % server_name),
        )

