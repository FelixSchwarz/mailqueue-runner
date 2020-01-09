# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import logging
import os

from boltons.fileutils import atomic_rename

from .message_utils import parse_message_envelope


__all__ = ['MessageHandler']

class MessageHandler(object):
    def __init__(self, mailer, delivery_log=None):
        self.mailer = mailer
        self.delivery_log = delivery_log or logging.getLogger('mailqueue.delivery_log')

    def send_message(self, file_path):
        fp = self._mark_message_as_in_progress(file_path)
        if fp is None:
            # e.g. invalid path
            return None
        msg = parse_message_envelope(fp)
        was_sent = self.mailer.send(msg.from_addr, msg.to_addrs, msg.msg_bytes)
        if was_sent:
            self._remove_message(fp)
            log_msg = '%s => %s' % (msg.from_addr, ', '.join(msg.to_addrs))
            self.delivery_log.info(log_msg)
        else:
            self._move_message_back_to_new(fp.name)
        return was_sent

    # --- internal functionality ----------------------------------------------
    def _mark_message_as_in_progress(self, source_path):
        return self._move_message(source_path, target_folder='cur')

    def _move_message_back_to_new(self, source_path):
        return self._move_message(source_path, target_folder='new')

    def _move_message(self, file_path, target_folder):
        folder_path = os.path.dirname(file_path)
        queue_base_dir = os.path.dirname(folder_path)
        filename = os.path.basename(file_path)
        target_path = os.path.join(queue_base_dir, target_folder, filename)
        try:
            # Bolton's "atomic_rename()" is compatible with Windows
            # Under Linux "atomic_rename()" ensures that the "target_path" file
            # contains the complete contents AND never overwrites an existing
            # file (as long as it is not stored on an NFS filesystem).
            # However the full operation is NOT atomic in Linux as it consists
            # of two system calls (link(), unlink()) so it could happen that
            # the file exists in the source folder AND the target folder (as
            # hard link).
            # The ideal solution would be to use "renameat2", a Linux-specific
            # system call which can rename without overwriting. However that
            # syscall comes with a number of caveats:
            # - not all file systems are supported (though I guess ext4 should
            #   be fine)
            # - not exposed in Python: need to write custom code
            # - only added in glibc 2.28 (released on 2018-08-01) so we would
            #   have to do a raw syscall from Python (doable, e.g. with the
            #   "execute-syscall" github project)
            # - added in Linux 3.15 - we can not use that syscall in CentOS 7
            #   (ships with kernel 3.10) which is pretty much a showstopper for me.
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

