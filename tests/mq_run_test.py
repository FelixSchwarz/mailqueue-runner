# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import os
from unittest import mock

from dotmap import DotMap
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



@pytest.mark.skipif(SignalRegistry is None, reason='requires PuzzlePluginSystem')
def test_mq_run_failed_delivery_with_plugins(tmp_path):
    queue_basedir = os.path.join(str(tmp_path), 'mailqueue')
    create_maildir_directories(queue_basedir)
    inject_example_message(queue_basedir)

    mock_fn = mock.MagicMock(return_value=MQAction.DISCARD, spec={})
    signal_map = {MQSignal.delivery_failed: mock_fn}
    fake_plugin = create_fake_plugin(signal_map)
    fake_entry_points = create_fake_entry_points('testplugin', fake_plugin)
    config_path = create_ini('host.example', port=12345, dir_path=str(tmp_path))

    cmd = ['mq-run', f'--config={config_path}', queue_basedir]
    mailer = DebugMailer(simulate_failed_sending=True)
    # mock the `entry_points()` function in PuzzlePlugins so it contains only
    # our fake plugin and nothing is picked up from the system.
    _mocked_symbol = 'schwarz.puzzle_plugins.plugin_loader.entry_points'
    with mock.patch(_mocked_symbol, return_value=fake_entry_points):
        rc = one_shot_queue_run_main(argv=cmd, return_rc_code=True)
    assert rc == 0

    assert len(mailer.sent_mails) == 0
    mock_fn.assert_called_once()
    assert len(tuple(find_messages(queue_basedir, log=l_(None)))) == 0, \
        'plugin should have discarded the message after failed delivery'


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


def create_fake_entry_points(plugin_id, plugin):
    """Create a fake entry_points() return value for importlib.metadata."""
    class FakeEntryPoint:
        def __init__(self, name, value, group):
            self.name = name
            self.value = value
            self.module, self.attr = value.split(':')
            self.group = group

        def load(self):
            return plugin

    # `importlib.metadata.entry_points()` returns an `EntryPoints` instance
    # (or `dict` in older versions of Python).
    # We'll mimic the modern API `entry_points().select(group='mailqueue.plugins')`
    # while still maintaining some compatibility with older versions.
    fake_ep = FakeEntryPoint(plugin_id, 'dummy_module:DummyPlugin', 'mailqueue.plugins')

    class FakeEntryPoints:
        def select(self, group=None):
            return [fake_ep] if (group == 'mailqueue.plugins') else []

        def get(self, name, default=None):
            return fake_ep if name == plugin_id else default

    return FakeEntryPoints()
