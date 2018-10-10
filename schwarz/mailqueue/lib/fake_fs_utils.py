# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import os
import tempfile
import shutil


__all__ = ['FakeFS', 'TempFS']

class FakeFS(object):
    def __init__(self, patcher):
        self._stubber = patcher

    @classmethod
    def set_up(cls, test=None):
        # only require pyfakefs if it is actually used
        from pyfakefs.fake_filesystem_unittest import Patcher
        stubber = Patcher()
        stubber.setUp()
        fake_fs = FakeFS(stubber)
        if test:
            test.addCleanup(fake_fs.tear_down)
        return fake_fs

    def tear_down(self):
        self._stubber.tearDown()

    def __getattr__(self, name):
        mapping = {
            'create_directory': self._stubber.fs.CreateDirectory,
            'create_file': self._stubber.fs.CreateFile,
        }
        if name in mapping:
            return mapping[name]
        if hasattr(self._stubber.fs, name):
            return getattr(self._stubber.fs, name)
        klassname = self.__class__.__name__
        raise AttributeError("AttributeError: %s object has no attribute %r" % (klassname, name))


class TempFS(object):
    def __init__(self, tempdir):
        self.root = tempdir

    @classmethod
    def set_up(cls, test=None):
        temp_path = tempfile.mkdtemp()
        temp_fs = TempFS(temp_path)
        if test:
            test.addCleanup(temp_fs.tear_down)
        return temp_fs

    def tear_down(self):
        shutil.rmtree(self.root)

    def create_directory(self, dirname):
        if dirname.startswith(self.root):
            path = dirname
        else:
            if dirname.startswith(os.sep):
                dirname = dirname[len(os.sep):]
            path = os.path.join(self.root, dirname)
        os.makedirs(path)
        return path

    def create_file(self, path):
        with open(path, 'w') as fp:
            fp.write('')

