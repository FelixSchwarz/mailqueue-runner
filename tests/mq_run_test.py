# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import os
from unittest import mock

from dotmap import DotMap
from pkg_resources import Distribution, EntryPoint, WorkingSet
from schwarz.log_utils import l_


try:
    from schwarz.puzzle_plugins import SignalRegistry, connect_signals, disconnect_signals
except ImportError:
    SignalRegistry = None
import pytest

from schwarz.mailqueue import (
    DebugMailer,
    MQAction,
    MQSignal,
    app_helpers,
    create_maildir_directories,
)
from schwarz.mailqueue.cli import one_shot_queue_run_main
from schwarz.mailqueue.maildir_utils import find_messages
from schwarz.mailqueue.testutils import create_ini, inject_example_message


@pytest.mark.parametrize('failed_sending', [False, True])
def test_mq_run_delivery_without_plugins(failed_sending, tmp_path):
    queue_basedir = str(tmp_path / 'mailqueue')
    create_maildir_directories(queue_basedir)
    inject_example_message(queue_basedir)
    config_path = create_ini('host.example', port=12345, dir_path=tmp_path, log_dir=tmp_path)

    cmd = ['mq-run', f'--config={config_path}', queue_basedir]
    mailer = DebugMailer(simulate_failed_sending=failed_sending)
    with mock.patch('schwarz.mailqueue.queue_runner.init_smtp_mailer', new=lambda s: mailer):
        rc = one_shot_queue_run_main(argv=cmd, return_rc_code=True)
    assert rc == 0

    queued_messages = tuple(find_messages(queue_basedir, log=l_(None)))
    path_delivery_log = tmp_path / 'mq_delivery.log'
    path_queue_log = tmp_path / 'mq_queue.log'
    if failed_sending:
        assert len(mailer.sent_mails) == 0
        assert len(queued_messages) == 1, 'message should have been queued for later delivery'
        assert path_delivery_log.read_text() == ''
        assert path_queue_log.read_text() == ''
    else:
        assert len(mailer.sent_mails) == 1
        assert len(queued_messages) == 0
        log_line, = path_delivery_log.read_text().splitlines()
        assert 'foo@site.example => bar@site.example' in log_line
        assert path_queue_log.read_text() == ''



# entries=() so the WorkingSet contains our entries only, nothing is
# picked up from the system
@mock.patch('schwarz.mailqueue.app_helpers._working_set', new=WorkingSet(entries=()))
@pytest.mark.skipif(SignalRegistry is None, reason='requires PuzzlePluginSystem')
def test_mq_run_failed_delivery_with_plugins(tmp_path):
    queue_basedir = os.path.join(str(tmp_path), 'mailqueue')
    create_maildir_directories(queue_basedir)
    inject_example_message(queue_basedir)

    mock_fn = mock.MagicMock(return_value=MQAction.DISCARD, spec={})
    signal_map = {MQSignal.delivery_failed: mock_fn}
    fake_plugin = create_fake_plugin(signal_map)
    inject_plugin_into_working_set('testplugin', fake_plugin)
    config_path = create_ini('host.example', port=12345, dir_path=str(tmp_path))

    cmd = ['mq-run', f'--config={config_path}', queue_basedir]
    mailer = DebugMailer(simulate_failed_sending=True)
    with mock.patch('schwarz.mailqueue.queue_runner.init_smtp_mailer', new=lambda s: mailer):
        rc = one_shot_queue_run_main(argv=cmd, return_rc_code=True)
    assert rc == 0

    assert len(mailer.sent_mails) == 0
    mock_fn.assert_called_once()
    assert len(tuple(find_messages(queue_basedir, log=l_(None)))) == 0, \
        'plugin should have discarded the message after failed delivery'


def inject_plugin_into_working_set(plugin_id, plugin):
    class FakeEntryPoint(EntryPoint):
        def load(self, *args, **kwargs):
            return plugin

    entry_point = FakeEntryPoint.parse(plugin_id + ' = dummy_module:DummyPlugin')
    dist = Distribution(version='1.0')
    dist._ep_map = {
        'mailqueue.plugins': {
            plugin_id: entry_point
        }
    }
    entry_point.dist = dist
    working_set = app_helpers._working_set
    working_set.add(dist, plugin_id)
    return working_set


def create_fake_plugin(signal_map):
    def fake_initialize(context, registry):
        _connected_signals = connect_signals(signal_map, registry)
        context.update({
            'signals': _connected_signals,
            'registry': registry,
        })

    def fake_terminate(context):
        _connected_signals = context['signals']
        _registry = context['registry']
        disconnect_signals(_connected_signals, _registry)

    fake_plugin = DotMap(
        _dynamic=False,
        initialize=fake_initialize,
        terminate=fake_terminate,
    )
    return fake_plugin
