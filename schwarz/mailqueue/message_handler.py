# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import logging
import os

from .maildir_utils import move_message
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
            self._log_successful_delivery(msg)
        else:
            self._move_message_back_to_new(fp.name)
        return was_sent

    # --- internal functionality ----------------------------------------------
    def _log_successful_delivery(self, msg):
        log_msg = '%s => %s' % (msg.from_addr, ', '.join(msg.to_addrs))
        if msg.msg_id:
            log_msg += ' <%s>' % msg.msg_id
        self.delivery_log.info(log_msg)

    def _mark_message_as_in_progress(self, source_path):
        return move_message(source_path, target_folder='cur')

    def _move_message_back_to_new(self, source_path):
        return move_message(source_path, target_folder='new')

    def _remove_message(self, fp):
        file_path = fp.name
        try:
            os.unlink(file_path)
        except OSError:
            pass
        fp.close()

