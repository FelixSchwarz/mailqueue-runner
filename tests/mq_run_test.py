# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os
try:
    from unittest import mock
except ImportError:
    import mock

from pkg_resources import Distribution, EntryPoint, WorkingSet
from pythonic_testcase import *
from schwarz.fakefs_helpers import TempFS
from schwarz.log_utils import l_
from schwarz.puzzle_plugins import connect_signals, disconnect_signals
from schwarz.puzzle_plugins.lib import AttrDict

from schwarz.mailqueue import (app_helpers, create_maildir_directories,
    DebugMailer, MQAction, MQSignal)
from schwarz.mailqueue.cli import one_shot_queue_run_main
from schwarz.mailqueue.maildir_utils import find_messages
from schwarz.mailqueue.testutils import create_ini, inject_example_message



class MQRunTest(PythonicTestCase):
    def setUp(self):
        self.fs = TempFS.set_up(test=self)

    # entries=() so the WorkingSet contains our entries only, nothing is
    # picked up from the system
    @mock.patch('schwarz.mailqueue.app_helpers._working_set', new=WorkingSet(entries=()))
    def test_mq_runner_can_load_plugins(self):
        queue_basedir = os.path.join(self.fs.root, 'mailqueue')
        create_maildir_directories(queue_basedir)
        inject_example_message(queue_basedir)

        mock_fn = mock.MagicMock(return_value=MQAction.DISCARD, spec={})
        signal_map = {MQSignal.delivery_failed: mock_fn}
        fake_plugin = create_fake_plugin(signal_map)
        inject_plugin_into_working_set('testplugin', fake_plugin)
        config_path = create_ini('host.example', port=12345, fs=self.fs)

        cmd = ['mq-run', config_path, queue_basedir]
        mailer = DebugMailer(simulate_failed_sending=True)
        with mock.patch('schwarz.mailqueue.queue_runner.init_smtp_mailer', new=lambda s: mailer):
            rc = one_shot_queue_run_main(argv=cmd, return_rc_code=True)
        assert_equals(0, rc)

        assert_length(0, mailer.sent_mails)
        mock_fn.assert_called_once()
        assert_length(0, find_messages(queue_basedir, log=l_(None)),
            message='plugin should have discarded the message after failed delivery')

    def test_mq_runner_works_without_plugins(self):
        queue_basedir = os.path.join(self.fs.root, 'mailqueue')
        create_maildir_directories(queue_basedir)
        inject_example_message(queue_basedir)
        config_path = create_ini('host.example', port=12345, fs=self.fs)

        cmd = ['mq-run', config_path, queue_basedir]
        mailer = DebugMailer(simulate_failed_sending=True)
        with mock.patch('schwarz.mailqueue.queue_runner.init_smtp_mailer', new=lambda s: mailer):
            rc = one_shot_queue_run_main(argv=cmd, return_rc_code=True)
        assert_equals(0, rc)

        assert_length(0, mailer.sent_mails)
        assert_length(1, find_messages(queue_basedir, log=l_(None)),
            message='message should have been queued for later delivery')



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

    fake_plugin = AttrDict({
        'initialize': fake_initialize,
        'terminate': fake_terminate,
    })
    return fake_plugin

