# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

from boltons.fileutils import atomic_rename, atomic_save

from .compat import os_makedirs


__all__ = ['create_maildir_directories', 'move_message']

def create_maildir_directories(basedir, is_folder=False):
    os_makedirs(basedir, 0o700, exist_ok=True)
    new_path = None
    for subdir_name in ('tmp', 'cur', 'new'):
        subdir_path = os.path.join(basedir, subdir_name)
        os_makedirs(subdir_path, 0o700, exist_ok=True)
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


def move_message(file_path, target_folder):
    folder_path = os.path.dirname(file_path)
    queue_base_dir = os.path.dirname(folder_path)
    filename = os.path.basename(file_path)
    target_path = os.path.join(queue_base_dir, target_folder, filename)
    try:
        # Bolton's "atomic_rename()" is compatible with Windows.
        # Under Linux "atomic_rename()" ensures that the "target_path" file
        # contains the complete contents AND never overwrites an existing
        # file (as long as it is not stored on an NFS filesystem).
        # However the full operation is NOT atomic in Linux as it consists of
        # two system calls (link(), unlink()) so it could happen that the file
        # exists in the source folder AND the target folder (as hard link).
        # The ideal solution would be to use "renameat2", a Linux-specific
        # system call which can rename without overwriting. However that
        # syscall comes with a number of caveats:
        # - not all file systems are supported (though I guess ext4 should be
        #   fine)
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
