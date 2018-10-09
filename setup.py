#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re

from setuptools import setup, find_packages


def requires_from_file(filename):
    requirements = []
    with open(filename, 'r') as requirements_fp:
        for line in requirements_fp.readlines():
            match = re.search('^\s*([a-zA-Z][^#]+?)(\s*#.+)?\n$', line)
            if match:
                requirements.append(match.group(1))
    return requirements

setup(
    name = 'mailqueue-runner',
    version = '0.1.20181009',
    license = 'MIT and Python',

    zip_safe = False,
    packages = find_packages(),
    namespace_packages = ['schwarz'],
    include_package_data = True,
    scripts = (
    ),

    install_requires=requires_from_file('requirements.txt'),
)
