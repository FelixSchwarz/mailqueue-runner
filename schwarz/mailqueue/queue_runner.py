# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

from .message_utils import parse_message_envelope


__all__ = ['MaildirQueueRunner']

class MaildirQueueRunner(object):
    def __init__(self, mailer, queue_dir):
        self.mailer = mailer
        self.queue_dir = queue_dir

    def send_messages(self, filenames):
        for file_path in filenames:
            self.send_message(file_path)

    def send_message(self, file_path):
        fp = self._mark_message_as_in_progress(file_path)
        from_addr, to_addrs, msg_fp = parse_message_envelope(fp)
        self.mailer.send(from_addr, to_addrs, msg_fp)
        self._remove_message(fp)

    # --- internal functionality ----------------------------------------------
    def _mark_message_as_in_progress(self, source_path):
        filename = os.path.basename(source_path)
        target_path = os.path.join(self.queue_dir, 'cur', filename)
        # Unix-only, possible Windows compatible replacement:
        # from boltons.fileutils import atomic_rename
        # atomic_rename(source_path, target_path, overwrite=False)
        os.link(source_path, target_path)
        os.unlink(source_path)
        fp = open(target_path, 'rb+')
        return fp

    def _remove_message(self, fp):
        file_path = fp.name
        os.unlink(file_path)
        fp.close()

