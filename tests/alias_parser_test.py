# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import textwrap
from io import StringIO

import pytest

from schwarz.mailqueue.aliases_parser import _parse_aliases, lookup_address


def test_lookup_adress_simple_match():
    result = lookup_address('foo', _aliases={'foo': ['foo@site.example']})
    assert result == ('foo@site.example',)


def test_lookup_adress_full_email_adress():
    # regular email address -> should not use aliases
    result = lookup_address('foo@site.example', _aliases={'foo': ['bar@site.example']})
    assert result == ('foo@site.example',)


@pytest.mark.parametrize('aliases', [
    {},
    {'bar': ['bar@site.example']}
])
def test_lookup_adress_no_match(aliases):
    result = lookup_address('foo', _aliases=aliases)
    assert result is None


def test_lookup_adress_recursive_lookup():
    aliases = {
        'foo': ['bar'],
        'bar': ['baz'],
        'baz': ['info@site.example'],
    }
    result = lookup_address('foo', _aliases=aliases)
    assert result == ('info@site.example',)


def test_lookup_multiple_addresses():
    aliases = {
        'admins': ['foo', 'bar'],
        'foo': ['foo@site.example'],
        'bar': ['bar@site.example'],
    }
    result = lookup_address('admins', _aliases=aliases)
    assert result == ('foo@site.example', 'bar@site.example')


def test_lookup_address_multiple_aliases_to_same_email_address():
    aliases = {
        'admins': ['foo', 'bar'],
        'foo': ['staff@site.example'],
        'bar': ['staff@site.example'],
    }
    result = lookup_address('admins', _aliases=aliases)
    assert result == ('staff@site.example',)


def test_lookup_address_mixed_aliases():
    aliases = {
        'admins': ['foo', 'monitor@site.example'],
        'foo': ['staff'],
        'staff': ['staff@site.example'],
    }
    result = lookup_address('admins', _aliases=aliases)
    assert set(result) == set(['monitor@site.example', 'staff@site.example'])


def test_parse_aliases_empty_file():
    assert _parse_aliases(StringIO('')) == {}


def test_parse_aliases_single_alias():
    aliases = 'foo: foo@site.example'
    assert _parse_aliases(StringIO(aliases)) == {'foo': ['foo@site.example']}


def test_parse_aliases_comments_and_empty_lines():
    aliases = textwrap.dedent('''
        # comment
        foo  : \t bar

        \tbar: staff@site.example
        baz: root@site.example # some comment
    ''')
    expected_aliases = {
        'foo': ['bar'],
        'bar': ['staff@site.example'],
        'baz': ['root@site.example'],
    }
    assert _parse_aliases(StringIO(aliases)) == expected_aliases


def test_parse_aliases_multiple_targets():
    aliases = 'foo: foo@site.example, monitor@site.example'
    expected_aliases = {
        'foo': ['foo@site.example', 'monitor@site.example'],
    }
    assert _parse_aliases(StringIO(aliases)) == expected_aliases
