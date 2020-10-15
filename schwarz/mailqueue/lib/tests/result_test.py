# -*- coding: UTF-8 -*-
# Copyright 2019 Felix Schwarz
# SPDX-License-Identifier: MIT

from pythonic_testcase import *

from ..result import Result


class ResultTest(PythonicTestCase):
    def test_bool_returns_boolean_values(self):
        assert_is(bool(Result(True)), True)
        assert_is(bool(Result(False)), False)
        assert_is(bool(Result(None)), False)

    def test_can_set_attributes(self):
        result = Result(True, msg=None)
        result.msg = 'foo'
        assert_equals('foo', result.msg)
        assert_equals('foo', result.data['msg'])

    def test_result_supports_len(self):
        result = Result('foobar')
        assert_equals(6, len(result))
        assert_length(6, result)
