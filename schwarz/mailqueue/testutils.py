# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

from io import BytesIO
from mailbox import Maildir
import os


__all__ = ['build_queued_msg', 'inject_message']

def build_queued_msg(return_path=None, envelope_to=None, msg_bytes=None):
    if return_path is None:
        return_path = b'foo@site.example'
    if envelope_to is None:
        envelope_to = b'bar@site.example'
    if msg_bytes is None:
        msg_bytes = b'Header: somevalue\n\nMsgBody\n'
    msg = (
        b'Return-path: ' + return_path + b'\n'
        b'Envelope-to: ' + envelope_to + b'\n' + \
        msg_bytes
    )
    return BytesIO(msg)

def inject_message(path_maildir, msg_fp):
    msg_maildir_id = Maildir(path_maildir).add(msg_fp)
    msg_path = os.path.join(path_maildir, 'new', msg_maildir_id)
    return msg_path
