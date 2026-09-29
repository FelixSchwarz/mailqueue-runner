# SPDX-License-Identifier: MIT

import logging

from schwarz.mailqueue.testutils import FakeSSLContext, fake_smtp_client


DEBUG = logging.DEBUG

def test_can_log_connect(caplog):
    caplog.set_level(DEBUG, logger='s')
    smtp_log = logging.getLogger('s')
    client = fake_smtp_client(smtp_log=smtp_log)
    client.close()
    assert len(caplog.records) != 0, 'no records logged'
    assert caplog.record_tuples == [
        ('s', DEBUG, 'connecting to site.invalid:123'),
        ('s', DEBUG, '<= 220 mx.site.example ESMTP'),
    ]

def test_can_log_client_command(caplog):
    caplog.set_level(DEBUG, logger='s')
    smtp_log = logging.getLogger('s')
    client = fake_smtp_client(smtp_log=smtp_log)
    client.ehlo('client.example')
    client.quit()
    assert len(caplog.records) != 0, 'no records logged'
    assert caplog.record_tuples == [
        ('s', DEBUG, 'connecting to site.invalid:123'),
        ('s', DEBUG, '<= 220 mx.site.example ESMTP'),
        ('s', DEBUG, '=> EHLO client.example'),
        ('s', DEBUG, '<= 250-mx.site.example'),
        ('s', DEBUG, '<= 250-SIZE 33554432'),
        ('s', DEBUG, '<= 250-8BITMIME'),
        ('s', DEBUG, '<= 250 HELP'),
        ('s', DEBUG, '=> QUIT'),
        ('s', DEBUG, '<= 221 Bye'),
    ]

def test_can_log_complete_smtp_interaction(caplog):
    from_ = 'sender@site.example'
    to_ = 'recipient@site.example'
    msg = b'Header: value\n\nbody'
    caplog.set_level(DEBUG, logger='s')
    smtp_log = logging.getLogger('s')
    client = fake_smtp_client(smtp_log=smtp_log, local_hostname='client.example')
    client.sendmail(from_, to_, msg)
    client.quit()
    assert len(caplog.records) != 0, 'no records logged'
    assert caplog.record_tuples == [
        ('s', DEBUG, 'connecting to site.invalid:123'),
        ('s', DEBUG, '<= 220 mx.site.example ESMTP'),
        ('s', DEBUG, '=> EHLO client.example'),
        ('s', DEBUG, '<= 250-mx.site.example'),
        ('s', DEBUG, '<= 250-SIZE 33554432'),
        ('s', DEBUG, '<= 250-8BITMIME'),
        ('s', DEBUG, '<= 250 HELP'),
        ('s', DEBUG, '=> MAIL FROM:<%s> BODY=8BITMIME' % from_),
        ('s', DEBUG, '<= 250 OK'),
        ('s', DEBUG, '=> RCPT TO:<%s>' % to_),
        ('s', DEBUG, '<= 250 OK'),
        ('s', DEBUG, '=> DATA'),
        ('s', DEBUG, '<= 354 End data with <CR><LF>.<CR><LF>'),

        ('s', DEBUG, '=> Header: value'),
        ('s', DEBUG, '=> '),
        ('s', DEBUG, '=> body'),
        ('s', DEBUG, '=> .'),

        ('s', DEBUG, '<= 250 OK'),
        ('s', DEBUG, '=> QUIT'),
        ('s', DEBUG, '<= 221 Bye'),
    ]

def test_can_log_connect_with_implicit_tls(caplog):
    caplog.set_level(DEBUG, logger='s')
    smtp_log = logging.getLogger('s')
    client = fake_smtp_client(smtp_log=smtp_log, implicit_tls=True, ssl_context=FakeSSLContext())
    client.close()
    assert caplog.record_tuples == [
        ('s', DEBUG, 'connecting to site.invalid:123 (implicit TLS)'),
        ('s', DEBUG, '<= 220 mx.site.example ESMTP'),
    ]
