# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import logging
import socket

from testfixtures import LogCapture

from schwarz.mailqueue.testutils import fake_smtp_client


def test_can_log_connect():
    with LogCapture() as lc:
        smtp_log = logging.getLogger('s')
        _ = fake_smtp_client(smtp_log=smtp_log)
    assert len(lc.records) != 0, 'no records logged'
    # pymta shortcoming: unable to set the server host name manually
    server_name = socket.getfqdn()
    lc.check(
        ('s', 'DEBUG', 'connecting to site.invalid:123'),
        ('s', 'DEBUG', '<= 220 %s Hello 127.0.0.1' % server_name),
    )

def test_can_log_client_command():
    with LogCapture() as lc:
        smtp_log = logging.getLogger('s')
        client = fake_smtp_client(smtp_log=smtp_log)
        client.ehlo('client.example')
        client.quit()
    assert len(lc.records) != 0, 'no records logged'
    # pymta shortcoming: unable to set the server host name manually
    server_name = socket.getfqdn()
    lc.check(
        ('s', 'DEBUG', 'connecting to site.invalid:123'),
        ('s', 'DEBUG', '<= 220 %s Hello 127.0.0.1' % server_name),
        ('s', 'DEBUG', '=> EHLO client.example'),
        ('s', 'DEBUG', '<= 250-%s' % server_name),
        ('s', 'DEBUG', '<= 250 HELP'),
        ('s', 'DEBUG', '=> QUIT'),
        ('s', 'DEBUG', '<= 221 %s closing connection' % server_name),
    )

def test_can_log_complete_smtp_interaction():
    from_ = 'sender@site.example'
    to_ = 'recipient@site.example'
    msg = b'Header: value\n\nbody'
    with LogCapture() as lc:
        smtp_log = logging.getLogger('s')
        client = fake_smtp_client(smtp_log=smtp_log, local_hostname='client.example')
        client.sendmail(from_, to_, msg)
        client.quit()
    assert len(lc.records) != 0, 'no records logged'
    # pymta shortcoming: unable to set the server host name manually
    server_name = socket.getfqdn()
    lc.check(
        ('s', 'DEBUG', 'connecting to site.invalid:123'),
        ('s', 'DEBUG', '<= 220 %s Hello 127.0.0.1' % server_name),
        ('s', 'DEBUG', '=> EHLO client.example'),
        ('s', 'DEBUG', '<= 250-%s' % server_name),
        ('s', 'DEBUG', '<= 250 HELP'),
        ('s', 'DEBUG', '=> MAIL FROM:<%s>' % from_),
        ('s', 'DEBUG', '<= 250 OK'),
        ('s', 'DEBUG', '=> RCPT TO:<%s>' % to_),
        ('s', 'DEBUG', '<= 250 OK'),
        ('s', 'DEBUG', '=> DATA'),
        ('s', 'DEBUG', '<= 354 Enter message, ending with "." on a line by itself'),

        ('s', 'DEBUG', '=> Header: value'),
        ('s', 'DEBUG', '=> '),
        ('s', 'DEBUG', '=> body'),
        ('s', 'DEBUG', '=> .'),

        ('s', 'DEBUG', '<= 250 OK'),
        ('s', 'DEBUG', '=> QUIT'),
        ('s', 'DEBUG', '<= 221 %s closing connection' % server_name),
    )
