# SPDX-License-Identifier: MIT

import email
import random
import subprocess
import sys
from email.utils import parsedate_to_datetime

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


def test_mq_mail(ctx):
    mail_params = [
        '--from-address=dbuser@worker.example',
        '--subject=Mail »Subject«',  # subject contains non-ascii characters
        'foo@site.example',
    ]
    _mq_mail(mail_params, msg_body='mail body', ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    # smtp from is auto-generated from current user+host, so not easy to test
    assert tuple(smtp_msg.smtp_to) == ('foo@site.example',)
    assert smtp_msg.username is None  # no smtp user name set in config

    msg = email.message_from_string(smtp_msg.msg_data)
    assert msg['To'] == 'foo@site.example'
    subject_header = msg['Subject']
    assert subject_header.upper().startswith('=?UTF-8?Q?')
    assert _decode_header(subject_header) == 'Mail »Subject«'
    assert msg['From'] == 'dbuser@worker.example'
    msg_date = parsedate_to_datetime(msg['Date'])
    assert almost_now(msg_date)
    assert msg['Message-ID']
    assert msg['Mime-Version'] == '1.0'
    assert msg['Content-Transfer-Encoding'] == '8bit'
    assert msg['Content-Type'] == 'text/plain; charset="UTF-8"'
    assert msg.get_payload() == 'mail body'

def _decode_header(header_value):
    header_parts = email.header.decode_header(header_value)
    strs = [str_part.decode(part_encoding) for (str_part, part_encoding) in header_parts]
    return ''.join(strs)

def test_mq_mail_with_aliases(ctx, tmp_path):
    aliases = {
        'dbuser': 'staff@site.example',
        'root': 'operations@corp.example',
    }
    aliases_path = create_alias_file(aliases, tmp_path)

    mail_params = [f'--aliases={aliases_path}', '-r', 'dbuser', 'root']
    _mq_mail(mail_params, msg_body='mail body', ctx=ctx)

    smtp_msg = retrieve_sent_message(ctx.mta)
    expected_recipient = aliases['root']

    assert tuple(smtp_msg.smtp_to) == (expected_recipient,)
    msg = email.message_from_string(smtp_msg.msg_data)
    assert msg['To'] == expected_recipient
    assert msg['From'] == aliases['dbuser']


def test_mq_mail_with_queuing(tmp_path):
    unused_port = random.randint(60000, 65535)
    queue_dir = tmp_path / 'queue'
    config_path = create_ini(
        'localhost',
        port      = unused_port,
        dir_path  = tmp_path,
        queue_dir = queue_dir,
    )
    mail_params = [
        '--from-address=dbuser@worker.example',
        '--subject=Mail Subject',
        'foo@site.example',
    ]
    _mq_mail(mail_params, msg_body='mail body', config_path=config_path)

    fs_queue = assemble_queue_with_new_messages(queue_dir, log=l_(None))
    assert fs_queue.qsize() == 1
    path_queued_msg = fs_queue.get()
    queued_msg = MaildirBackedMsg(path_queued_msg)
    assert queued_msg.to_addrs == ('foo@site.example',)
    assert bool(queued_msg.msg_id)
    assert queued_msg.retries == 0
    msg = email.message_from_bytes(queued_msg.msg_bytes)
    assert msg['From'] == 'dbuser@worker.example'
    assert msg['To'] == 'foo@site.example'


def _mq_mail(mail_params, msg_body, *, ctx=None, config_path=None):
    if config_path is None:
        cfg_dir = str(ctx.tmp_path)
        config_path = create_ini(ctx.hostname, ctx.listen_port, dir_path=cfg_dir)

    cli_params = [f'--config={config_path}'] + mail_params
    cmd = [sys.executable, '-m', 'schwarz.mailqueue.mq_mail'] + cli_params
    msg_body = msg_body.encode('utf-8')
    if sys.version_info >= (3, 7):
        proc = subprocess.run(cmd, input=msg_body, capture_output=True)
    else:
        proc = subprocess.run(cmd, input=msg_body, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if proc.returncode != 0:
        if proc.stdout:
            sys.stderr.buffer.write(proc.stdout)
        if proc.stderr:
            sys.stderr.buffer.write(proc.stderr)
        assert proc.returncode == 0
    if proc.stderr:
        raise AssertionError(proc.stderr)
    assert not proc.stdout
