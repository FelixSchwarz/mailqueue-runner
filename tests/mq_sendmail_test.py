# SPDX-License-Identifier: MIT

import email
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime as DateTime, timedelta as TimeDelta, timezone
from email.utils import parsedate_to_datetime

import pytest
from dotmap import DotMap
from pymta.test_util import SMTPTestHelper
from schwarz.log_utils import l_

from schwarz.mailqueue.queue_runner import MaildirBackedMsg, assemble_queue_with_new_messages
from schwarz.mailqueue.testutils import create_ini


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


def _example_message(to) -> str:
    base_msg = textwrap.dedent('''
        Subject: Test message

        Mail body
    ''').strip()
    to_line = f'To: {to}\n' if to else ''
    return to_line + base_msg


def test_mq_sendmail(ctx):
    rfc_msg = _example_message(to='baz@site.example')
    _mq_sendmail(['foo@site.example'], msg=rfc_msg, ctx=ctx)

    smtp_msg = _retrieve_sent_message(ctx.mta)
    # smtp from is auto-generated from current user+host, so not easy to test
    assert tuple(smtp_msg.smtp_to) == ('foo@site.example',)
    assert smtp_msg.username is None  # no smtp user name set in config
    assert smtp_msg.msg_data == rfc_msg


def _retrieve_sent_message(mta):
    received_queue = mta.get_received_messages()
    assert received_queue.qsize() == 1
    smtp_msg = received_queue.get(block=False)
    return smtp_msg


@pytest.mark.parametrize('set_via', ['config', 'cli-param'])
def test_mq_sendmail_set_from(ctx, set_via):
    smtp_sender = 'sender@host.example'
    cfg_from = smtp_sender if (set_via == 'config') else None
    config_path = create_ini(ctx.hostname, ctx.listen_port, ctx.tmp_path, from_=cfg_from)

    rfc_msg = _example_message(to='baz@site.example')
    _cmd = [f'--from={smtp_sender}'] if set_via == 'cli-param' else []
    _mq_sendmail(_cmd + ['foo@site.example'], msg=rfc_msg, config_path=config_path)

    smtp_msg = _retrieve_sent_message(ctx.mta)
    assert smtp_msg.smtp_from == smtp_sender
    assert tuple(smtp_msg.smtp_to) == ('foo@site.example',)
    assert smtp_msg.username is None  # no smtp user name set in config
    assert smtp_msg.msg_data == rfc_msg


def test_mq_sendmail_can_add_headers(ctx):
    sent_msg = _example_message(to='baz@site.example')
    cli_params = [
        '--set-from-header',
        '--set-date-header',
        '--set-msgid-header',
        'foo@site.example',
    ]
    _mq_sendmail(cli_params, msg=sent_msg, ctx=ctx)

    smtp_msg = _retrieve_sent_message(ctx.mta)
    msg = email.message_from_string(smtp_msg.msg_data)
    assert msg['To'] == 'baz@site.example'
    assert _is_email_address(msg['From'])
    msg_date = parsedate_to_datetime(msg['Date'])
    assert _almost_now(msg_date)
    assert msg['Message-ID']

def _almost_now(dt):
    return dt - DateTime.now(timezone.utc) < TimeDelta(seconds=1)

def _is_email_address(s):
    pattern = r'^\w+@[\w.\-]+$'
    return re.match(pattern, s) is not None


def test_mq_sendmail_with_aliases(ctx, tmp_path):
    aliases_path = _create_alias_file({'foo': 'staff@site.example'}, tmp_path)

    rfc_msg = _example_message(to='baz@site.example')
    _mq_sendmail([f'--aliases={aliases_path}', 'foo'], msg=rfc_msg, ctx=ctx)

    smtp_msg = _retrieve_sent_message(ctx.mta)
    expected_recipient = 'staff@site.example'
    assert tuple(smtp_msg.smtp_to) == (expected_recipient,)
    assert smtp_msg.msg_data == rfc_msg
    msg = email.message_from_string(smtp_msg.msg_data)
    # "From" header should not be changed by mq_sendmail
    assert msg['To'] == 'baz@site.example'


def _create_alias_file(aliases, dir_path) -> str:
    aliases_contents = ''
    for alias, target in aliases.items():
        aliases_contents += f'{alias}: {target}\n'

    aliases_path = dir_path / 'aliases'
    aliases_path.write_text(aliases_contents)
    return str(aliases_path)


def test_mq_sendmail_with_queuing(ctx):
    rfc_msg = _example_message(to='baz@site.example')
    unused_port = ctx.listen_port + 1
    queue_dir = ctx.tmp_path / 'queue'
    config_path = create_ini(
        ctx.hostname,
        port      = unused_port,
        dir_path  = ctx.tmp_path,
        queue_dir = queue_dir,
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


def _to_platform_bytes(msg_str: str) -> bytes:
    return msg_str.replace('\n', os.linesep).encode('utf-8')


def _mq_sendmail(cli_params, msg, *, ctx=None, config_path=None):
    if config_path is None:
        cfg_dir = str(ctx.tmp_path)
        config_path = create_ini(ctx.hostname, ctx.listen_port, dir_path=cfg_dir)

    cli_params = [f'--config={config_path}'] + cli_params
    cmd = [sys.executable, '-m', 'schwarz.mailqueue.mq_sendmail'] + cli_params
    msg_bytes = msg.encode('utf-8')
    if sys.version_info >= (3, 7):
        proc = subprocess.run(cmd, input=msg_bytes, capture_output=True)
    else:
        proc = subprocess.run(cmd, input=msg_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if proc.returncode != 0:
        if proc.stdout:
            sys.stderr.buffer.write(proc.stdout)
        if proc.stderr:
            sys.stderr.buffer.write(proc.stderr)
        assert proc.returncode == 0
    if proc.stderr:
        raise AssertionError(proc.stderr)
    assert not proc.stdout
