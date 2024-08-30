# SPDX-License-Identifier: MIT

import email
import email.utils
import os
import re
import subprocess
import sys
import textwrap
from email.header import Header

import pytest
from dotmap import DotMap
from pymta.test_util import SMTPTestHelper
from schwarz.log_utils import l_

from schwarz.mailqueue.queue_runner import MaildirBackedMsg, assemble_queue_with_new_messages
from schwarz.mailqueue.testutils import (
    almost_now,
    create_alias_file,
    create_ini,
    retrieve_sent_message,
)


@pytest.fixture
def ctx(tmp_path):
    mta_helper = SMTPTestHelper()
    (hostname, listen_port) = mta_helper.start_mta()
    ctx = {
        'hostname': hostname,
        'listen_port': listen_port,
        'mta': mta_helper,
        'tmp_path': tmp_path,
    }
    try:
        yield DotMap(_dynamic=False, **ctx)
    finally:
        mta_helper.stop_mta()


def _example_message(to=None, cc=None, bcc=None) -> str:
    base_msg = textwrap.dedent('''
        Subject: Test message

        Mail body
    ''').strip()
    to_line = f'To: {to}\n' if to else ''
    cc_line = f'CC: {cc}\n' if cc else ''
    bcc_line = f'BCC: {bcc}\n' if bcc else ''
    return to_line + cc_line + bcc_line + base_msg


def test_mq_sendmail(ctx):
    rfc_msg = _example_message(to='baz@site.example')
    _mq_sendmail(['foo@site.example'], msg=rfc_msg, ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    assert tuple(smtp_msg.smtp_to) == ('foo@site.example',)
    assert smtp_msg.username is None  # no smtp user name set in config
    assert smtp_msg.msg_data == rfc_msg

    path_delivery_log = ctx.tmp_path / 'mq_delivery.log'
    assert path_delivery_log.exists()
    log_line, = path_delivery_log.read_text().splitlines()
    assert 'testuser@host.example => foo@site.example' in log_line


@pytest.mark.parametrize('set_via', ['config', 'cli-param'])
def test_mq_sendmail_set_from(ctx, set_via):
    smtp_sender = 'sender@host.example'
    cfg_from = smtp_sender if (set_via == 'config') else None
    config_path = create_ini(ctx.hostname, ctx.listen_port, ctx.tmp_path, from_=cfg_from)

    rfc_msg = _example_message(to='baz@site.example')
    _cmd = [f'--from={smtp_sender}'] if set_via == 'cli-param' else []
    _mq_sendmail(_cmd + ['foo@site.example'], msg=rfc_msg, config_path=config_path)

    smtp_msg = retrieve_sent_message(ctx.mta)
    assert smtp_msg.smtp_from == smtp_sender
    assert tuple(smtp_msg.smtp_to) == ('foo@site.example',)
    assert smtp_msg.username is None  # no smtp user name set in config
    assert smtp_msg.msg_data == rfc_msg


def test_mq_sendmail_can_add_headers(ctx):
    sent_msg = _example_message(to=None)
    cli_params = [
        '--set-from-header',
        '--set-date-header',
        '--set-msgid-header',
        '--set-to-header',
        'foo@site.example',
    ]
    _mq_sendmail(cli_params, msg=sent_msg, ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    msg = email.message_from_string(smtp_msg.msg_data)
    assert msg['To'] == 'foo@site.example'
    assert _is_email_address(msg['From'])
    msg_date = email.utils.parsedate_to_datetime(msg['Date'])
    assert almost_now(msg_date)
    assert msg['Message-ID']


def _is_email_address(s):
    pattern = r'^\w+@[\w.\-]+$'
    return re.match(pattern, s) is not None


@pytest.mark.parametrize('long_option', [True, False])
def test_mq_sendmail_read_recipients_optional_parameter(ctx, long_option):
    msg = _example_message(
        to='to@site.example',
        cc='cc1@site.example, cc2@site.example',
        bcc='bcc@site.example',
    )
    cli_params = [
        '--read-recipients' if long_option else '-t',
        # no positional "recipient" parameter to ensure it is optional
    ]
    _mq_sendmail(cli_params, msg=msg, ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    expected_recipients = {
        'to@site.example',
        'cc1@site.example',
        'cc2@site.example',
        'bcc@site.example',
    }
    assert set(smtp_msg.smtp_to) == expected_recipients


@pytest.mark.parametrize('header', ['To', 'CC', 'BCC'])
def test_mq_sendmail_read_recipients_missing_headers(ctx, header):
    # not all headers are present in the message, should not crash
    msg_str = _example_message(**{header.lower(): 'foo@site.example'})
    # check test setup
    msg = email.message_from_string(msg_str)
    for missing_header in ({'To', 'CC', 'BCC'} - {header}):
        assert msg[missing_header] is None, f'header "{header}" should not be present'

    cli_params = [
        '--read-recipients',
    ]
    _mq_sendmail(cli_params, msg=msg_str, ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    assert set(smtp_msg.smtp_to) == {'foo@site.example'}


def test_mq_sendmail_recipient_required(ctx):
    msg = _example_message()
    cli_params = [
        '--read-recipients',
        # no positional "recipient" parameter
    ]
    proc = _mq_sendmail(cli_params, msg=msg, ctx=ctx, expect_error=True)

    assert proc.returncode == 1
    assert b'No recipient addresses found in message.' in proc.stderr


@pytest.mark.parametrize('duplicate_recipient', [True, False])
def test_mq_sendmail_read_recipients_deduplicate_recipients(ctx, duplicate_recipient):
    cc_line = 'foo@site.example' if duplicate_recipient else None
    msg = _example_message(to='bar@site.example', cc=cc_line)
    cli_params = [
        '--read-recipients',
        'foo@site.example',
    ]
    _mq_sendmail(cli_params, msg=msg, ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    assert len(smtp_msg.smtp_to) == 2  # no duplicated recipients
    assert set(smtp_msg.smtp_to) == {'foo@site.example', 'bar@site.example'}


@pytest.mark.parametrize('recipient_name', ['Zoë Matthews', 'Bar, Foo'])
def test_mq_sendmail_read_recipients_decode_header(ctx, recipient_name):
    encoded_name = str(Header(recipient_name, 'utf-8'))
    to = email.utils.formataddr((encoded_name, 'zoe.matthews@site.example'))
    msg = _example_message(to=to)
    cli_params = [
        '--read-recipients',
    ]
    _mq_sendmail(cli_params, msg=msg, ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    assert tuple(smtp_msg.smtp_to) == ('zoe.matthews@site.example',)


def test_mq_sendmail_with_aliases(ctx):
    aliases_path = create_alias_file({'foo': 'staff@site.example'}, ctx.tmp_path)

    rfc_msg = _example_message(to='baz@site.example')
    _mq_sendmail([f'--aliases={aliases_path}', 'foo'], msg=rfc_msg, ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    expected_recipient = 'staff@site.example'
    assert tuple(smtp_msg.smtp_to) == (expected_recipient,)
    assert smtp_msg.msg_data == rfc_msg
    msg = email.message_from_string(smtp_msg.msg_data)
    # "From" header should not be changed by mq_sendmail
    assert msg['To'] == 'baz@site.example'


def test_mq_sendmail_with_queuing(ctx):
    rfc_msg = _example_message(to='baz@site.example')
    unused_port = ctx.listen_port + 1
    queue_dir = ctx.tmp_path / 'queue'
    config_path = create_ini(
        ctx.hostname,
        port      = unused_port,
        dir_path  = ctx.tmp_path,
        queue_dir = queue_dir,
        log_dir  = ctx.tmp_path,
    )
    _mq_sendmail(['foo@site.example'], msg=rfc_msg, config_path=config_path)

    received_queue = ctx.mta.get_received_messages()
    assert received_queue.qsize() == 0

    fs_queue = assemble_queue_with_new_messages(queue_dir, log=l_(None))
    assert fs_queue.qsize() == 1
    path_queued_msg = fs_queue.get()
    msg = MaildirBackedMsg(path_queued_msg)
    assert msg.to_addrs == ('foo@site.example',)
    assert msg.msg_id is None  # not added automatically
    assert msg.retries == 0
    assert msg.msg_bytes == _to_platform_bytes(rfc_msg)

    path_delivery_log = ctx.tmp_path / 'mq_delivery.log'
    assert path_delivery_log.exists()
    assert path_delivery_log.read_text() == ''


def _to_platform_bytes(msg_str: str) -> bytes:
    return msg_str.replace('\n', os.linesep).encode('utf-8')


def _mq_sendmail(cli_params, msg, *, ctx=None, config_path=None, expect_error=False):
    if config_path is None:
        tmp_path = ctx.tmp_path
        cfg_dir = str(tmp_path)
        config_path = create_ini(ctx.hostname, ctx.listen_port, dir_path=cfg_dir, log_dir=tmp_path)

    cli_params = [f'--config={config_path}'] + cli_params
    cmd = [sys.executable, '-m', 'schwarz.mailqueue.mq_sendmail'] + cli_params
    msg_bytes = msg.encode('utf-8')
    if sys.version_info >= (3, 7):
        proc = subprocess.run(cmd, input=msg_bytes, capture_output=True)
    else:
        proc = subprocess.run(cmd, input=msg_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if expect_error:
        return proc
    if proc.returncode != 0:
        if proc.stdout:
            sys.stdout.buffer.write(proc.stdout)
        if proc.stderr:
            sys.stderr.buffer.write(proc.stderr)
        raise AssertionError(f'mq-sendmail exited with returncode {proc.returncode}')
    if proc.stderr:
        raise AssertionError(proc.stderr)
    assert not proc.stdout
