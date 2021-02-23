# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os

from boltons.fileutils import atomic_rename, atomic_save
import portalocker

from .compat import os_makedirs, FileNotFoundError, IS_WINDOWS


__all__ = ['create_maildir_directories', 'lock_file', 'move_message']


class LockedFile(object):
    __slots__ = ('fp', 'lock', 'name')
    def __init__(self, fp, lock=None):
        self.fp = fp
        self.lock = lock
        self.name = fp.name

    def close(self):
        self.fp.close()
        self.lock = None

    def is_locked(self):
        return (self.lock and (self.lock.fh is not None))

    def read(self, *args, **kwargs):
        return self.fp.read(*args, **kwargs)

    def readline(self):
        return self.fp.readline()

    def seek(self, pos):
        self.fp.seek(pos)

    def truncate(self):
        assert self.is_locked()
        self.fp.truncate()

    def write(self, data):
        assert self.is_locked()
        self.fp.write(data)


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


def is_path_like(path):
    if hasattr(os, 'PathLike'):
        return isinstance(path, os.PathLike)
    # support Python 2 with pathlib2
    return hasattr(path, '__fspath__')


def find_messages(queue_basedir, log, queue_folder='new'):
    if is_path_like(queue_basedir) and not hasattr(os, 'PathLike'):
        queue_basedir = str(queue_basedir)
    path_new = os.path.join(queue_basedir, queue_folder)
    try:
        filenames = os.listdir(path_new)
    except FileNotFoundError:
        log.error('Queue directory %s does not exist.', path_new)
    else:
        for filename in filenames:
            path = os.path.join(path_new, filename)
            yield path


def lock_file(path, timeout=None):
    try:
        previous_inode = os.stat(path).st_ino
    except OSError:
        # <path> does not exist at all
        return None
    lock = portalocker.Lock(path, mode='rb+', timeout=timeout)

    # prevent race condition when trying to lock file which is deleted by
    # another process (Linux/Unix):
    # https://stackoverflow.com/questions/17708885/flock-removing-locked-file-without-race-condition
    nr_tries = 3
    for i in range(nr_tries):
        try:
            fp = lock.acquire()
        except portalocker.LockException:
            continue
        # Need to check that the inodes of the opened file and the current file
        # in the file system are the same.
        try:
            current_inode = os.stat(path).st_ino
        except OSError:
            return None
        if current_inode == previous_inode:
            break
        previous_inode = current_inode
        lock.release()
    else:
        return None
    return LockedFile(fp, lock)

def move_message(file_, target_folder, open_file=True):
    if hasattr(file_, 'lock') and file_.is_locked():
        locked_file = file_
        file_path = file_.name
        assert (not IS_WINDOWS)
    else:
        locked_file = None
        # on Windows we don't use the LockedFile wrapper so we might get plain
        # file-like object here.
        file_path = file_ if (not hasattr(file_, 'name')) else file_.name
    folder_path = os.path.dirname(file_path)
    queue_base_dir = os.path.dirname(folder_path)
    filename = os.path.basename(file_path)
    target_path = os.path.join(queue_base_dir, target_folder, filename)
    if file_path == target_path:
        if not open_file:
            return target_path
        return file_

    did_open_file = False
    # no locking on Windows as you can not unlink/move open files there.
    if not IS_WINDOWS:
        if not locked_file:
            # acquire lock to ensure that no other process is handling this message
            # currently.
            locked_file = lock_file(file_path, timeout=0)
            did_open_file = True
        if locked_file is None:
            return None
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
        if open_file:
            if IS_WINDOWS:
                return open(target_path, 'rb+')
            # reflect the new location in LockedFile wrapper
            locked_file.name = target_path
            return locked_file
        elif did_open_file:
            # Closing the "LockedFile" will also release locks.
            # Only close the file if we actually opened it.
            locked_file.close()
        return target_path
    except (IOError, OSError):
        pass
    return None

