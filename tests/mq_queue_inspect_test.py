# SPDX-License-Identifier: MIT
import os
import sys
import tempfile
import shutil
import subprocess
import email
from pathlib import Path
import pytest
from schwarz.mailqueue.queue_runner import MaildirBackedMsg, assemble_queue_with_new_messages
from schwarz.mailqueue.testutils import create_ini, inject_example_message

def test_mq_queue_inspect_lists_queued_messages(tmp_path):
    queue_dir = tmp_path / 'queue'
    queue_dir.mkdir()
    config_path = create_ini('localhost', port=2525, dir_path=tmp_path, queue_dir=queue_dir)
    # Beispielnachricht in die Queue legen
    inject_example_message(queue_dir)
    # CLI-Tool aufrufen
    result = subprocess.run([
        sys.executable, '-m', 'schwarz.mailqueue.mq_queue_inspect',
        f'--config={config_path}'
    ], capture_output=True, text=True)
    assert result.returncode == 0
    # Es sollte mindestens eine Nachricht in der Ausgabe erscheinen
    assert 'Nachrichten in' in result.stdout
    assert 'From:' in result.stdout
    assert 'To:' in result.stdout
    assert 'Message-ID:' in result.stdout
    assert 'Retries:' in result.stdout
    assert 'Last Attempt:' in result.stdout
