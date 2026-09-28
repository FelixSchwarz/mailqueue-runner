#!/usr/bin/env python3
#
# SPDX-License-Identifier: MIT
# AI generated script so there is no copyright on this script. In case your
# jurisdiction is different, use MIT.
#
# /// script
# requires-python = ">= 3.9"
# dependencies = []
# ///
"""Check that the rpm spec file matches the version in "VERSION.txt".

usage: check-rpm-version.py

"VERSION.txt" must contain a normalized PEP 440 version (e.g. "0.14.0",
"0.14.0rc1", "0.14.0.dev0") because that string is also used for the sdist
file name. The spec file must contain

    %global pypi_version <VERSION.txt>
    Version:        <rpm version>
    Release:        <release>%{?dist}

and the latest %changelog entry must end with "- <rpm version>-<release>".

The rpm version is derived from the Python version following the Fedora
packaging guidelines, so pre-releases sort before the final release:

    0.14.0.dev0 -> 0.14.0~dev0
    0.14.0rc1   -> 0.14.0~rc1
    0.14.0.post1 -> 0.14.0^post1
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


VERSION_FILE = Path('VERSION.txt')
SPEC_FILE = Path('rpm/mailqueue-runner.spec')

# normalized PEP 440 versions without epoch and local version label
PEP440_RE = re.compile(
    r'^\d+(?:\.\d+)*'
    r'(?P<pre>(?:a|b|rc)\d+)?'
    r'(?P<post>\.post\d+)?'
    r'(?P<dev>\.dev\d+)?$'
)


def rpm_version(py_version: str) -> str:
    match = PEP440_RE.match(py_version)
    assert match is not None
    version = py_version
    if match['pre']:
        version = version.replace(match['pre'], '~' + match['pre'], 1)
    if match['post']:
        version = version.replace('.post', '^post', 1)
    if match['dev']:
        version = version.replace('.dev', '~dev', 1)
    return version


def spec_value(spec: str, pattern: str) -> str | None:
    match = re.search(pattern, spec, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def check(py_version: str, spec: str) -> list[str]:
    if not PEP440_RE.match(py_version):
        return [
            f'{VERSION_FILE}: "{py_version}" is not a normalized PEP 440 version '
            '(e.g. "0.14.0.dev0" instead of "0.14.0dev")'
        ]

    expected_version = rpm_version(py_version)
    pypi_version = spec_value(spec, r'^%global\s+pypi_version\s+(\S+)')
    version = spec_value(spec, r'^Version:\s*(.+)$')
    release = spec_value(spec, r'^Release:\s*(.+?)(?:%\{\?dist\})?$')
    changelog = spec_value(spec, r'^%changelog\s*\n(\*.*)$')

    errors = []
    if pypi_version != py_version:
        errors.append(f'"%global pypi_version" is "{pypi_version}", expected "{py_version}"')
    if version != expected_version:
        errors.append(f'"Version" is "{version}", expected "{expected_version}"')
    if not (release and release.isdigit()):
        errors.append(f'"Release" should be a number followed by "%{{?dist}}", found "{release}"')
    elif not (changelog and changelog.endswith(f' - {expected_version}-{release}')):
        errors.append(
            f'latest %changelog entry should end with "- {expected_version}-{release}", '
            f'found "{changelog}"'
        )
    return [f'{SPEC_FILE}: {error}' for error in errors]


def main() -> int:
    py_version = VERSION_FILE.read_text().strip()
    errors = check(py_version, SPEC_FILE.read_text())
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
