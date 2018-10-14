# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

from boltons.fileutils import atomic_rename

from .message_utils import parse_message_envelope


__all__ = ['MaildirQueueRunner']

class MaildirQueueRunner(object):
    def __init__(self, mailer, queue_dir):
        self.mailer = mailer
        self.queue_dir = queue_dir

    def send_message(self, file_path):
        fp = self._mark_message_as_in_progress(file_path)
        if fp is None:
            # e.g. invalid path
            return None
        from_addr, to_addrs, msg_fp = parse_message_envelope(fp)
        was_sent = self.mailer.send(from_addr, to_addrs, msg_fp)
        if was_sent:
            self._remove_message(fp)
        else:
            self._move_message_back_to_new(fp.name)
        return was_sent

    # --- internal functionality ----------------------------------------------
    def _mark_message_as_in_progress(self, source_path):
        return self._move_message(source_path, target_folder='cur')

    def _move_message_back_to_new(self, source_path):
        return self._move_message(source_path, target_folder='new')

    def _move_message(self, file_path, target_folder):
        filename = os.path.basename(file_path)
        target_path = os.path.join(self.queue_dir, target_folder, filename)
        try:
            # Bolton's "atomic_rename()" is compatible with Windows
            atomic_rename(file_path, target_path, overwrite=False)
            fp = open(target_path, 'rb+')
        except (IOError, OSError):
            fp = None
        return fp

    def _remove_message(self, fp):
        file_path = fp.name
        try:
            os.unlink(file_path)
        except OSError:
            pass
        fp.close()

