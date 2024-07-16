# -*- coding: UTF-8 -*-
# Copyright 2019 Felix Schwarz
# SPDX-License-Identifier: MIT

from ..result import Result


def test_bool_returns_boolean_values():
    assert bool(Result(True)) is True
    assert bool(Result(False)) is False
    assert bool(Result(None)) is False

def test_can_set_attributes():
    result = Result(True, msg=None)
    result.msg = 'foo'
    assert result.msg == 'foo'
    assert result.data['msg'] == 'foo'

def test_result_supports_len():
    result = Result('foobar')
    assert len(result) == 6
