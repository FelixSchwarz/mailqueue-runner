# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

from boltons.fileutils import atomic_save


__all__ = ['create_maildir_directories']

def create_maildir_directories(basedir, is_folder=False):
    os.makedirs(basedir, 0o700, exist_ok=True)
    new_path = None
    for subdir_name in ('tmp', 'cur', 'new'):
        subdir_path = os.path.join(basedir, subdir_name)
        os.makedirs(subdir_path, 0o700, exist_ok=True)
        if subdir_name == 'new':
            new_path = subdir_path

    # The maildir++ description [1] mentions a "maildirfolder" file for each
    # subfolder. Dovecot does not create such a file but doing so seems
    # harmless.
    # http://www.courier-mta.org/imap/README.maildirquota.html
    if is_folder:
        maildirfolder_path = os.path.join(basedir, 'maildirfolder')
        # never overwrite an existing "maildirfolder" file (just being overcautious)
        # in Python 3 we could also use "open(..., 'xb')" and catch FileExistsError
        with atomic_save(maildirfolder_path, overwrite=False) as fp:
            pass
    return new_path
