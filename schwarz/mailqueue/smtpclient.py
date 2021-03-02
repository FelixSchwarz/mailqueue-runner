# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Python-2.0 or MIT
# The code in this file heavily relies on Python's smtplib so I guess licensing
# it under "Python License 2.0" is in order. However my own contributions
# can also be used under the MIT license.

from __future__ import absolute_import, print_function, unicode_literals

from contextlib import contextmanager
import logging
import re
import six
import socket

from .lib.smtplib_py37 import (
    _fix_eols,
    bCRLF,
    CRLF,
    SMTP,
    SMTPDataError,
    SMTPResponseException,
    SMTPSenderRefused
)


__all__ = ['SMTPClient', 'SMTPRecipientRefused']

class SMTPRecipientRefused(SMTPResponseException):
    def __init__(self, code, msg, recipient):
        self.smtp_code = code
        self.smtp_error = msg
        self.recipient = recipient
        self.args = (code, msg, recipient)


class SMTPClient(SMTP):
    def __init__(self, *args, **kwargs):
        self.smtp_log = kwargs.pop('smtp_log', None)
        if self.smtp_log:
            # ensure that "._print_debug()" is called whenever something interesting happens
            self.debuglevel = 1
        super(SMTPClient, self).__init__(*args, **kwargs)

    # ,------------------------------------------------------------------------
    # copied from "smtplib" shipped with Python 3.7
    # modified to raise SMTPRecipientRefused when ANY recipient was rejected
    # License: Python-2.0 (my changes: public domain or CC-0 - your choice)
    def sendmail(self, from_addr, to_addrs, msg, mail_options=(), rcpt_options=()):
        self.ehlo_or_helo_if_needed()
        esmtp_opts = []
        if isinstance(msg, six.string_types):
            msg = _fix_eols(msg).encode('ascii')
        if self.does_esmtp:
            if self.has_extn('size'):
                esmtp_opts.append("size=%d" % len(msg))
            for option in mail_options:
                esmtp_opts.append(option)
        (code, resp) = self.mail(from_addr, esmtp_opts)
        if code != 250:
            if code == 421:
                self.close()
            else:
                self._rset()
            raise SMTPSenderRefused(code, resp, from_addr)
        if isinstance(to_addrs, six.string_types):
            to_addrs = [to_addrs]
        for each in to_addrs:
            (code, resp) = self.rcpt(each, rcpt_options)
            if code == 421:
                self.close()
                raise SMTPRecipientRefused(code, resp, each)
            elif (code != 250) and (code != 251):
                self._rset()
                raise SMTPRecipientRefused(code, resp, each)
        (code, resp) = self.data(msg)
        if code != 250:
            if code == 421:
                self.close()
            else:
                self._rset()
            raise SMTPDataError(code, resp)
        #if we got here then all recipients got our mail
        return {}
    # `------------------------------------------------------------------------

    def connect(self, host='localhost', port=0, source_address=None):
        # smtplib's ".connect()" does not log anything useful, "._get_socket()"
        # gets all the interesting info anyway so we can just disable all
        # logging here.
        with disable_debug(self):
            return super(SMTPClient, self).connect(host=host, port=port, source_address=source_address)

    def _get_socket(self, host, port, timeout):
        # This wrapper method is big because it contains superior logging which
        # completely blows Python's smtplib out of the water:
        #  - timeout is never logged
        #  - SMTP_SSL does not log "source_address", SMTP always logs it (even if None)
        # I consider complete logging worth the price of a somewhat lengthy
        # method.
        if self.smtp_log:
            log_tmpl = 'connecting to %(host)s:%(port)s'
            optional = []
            if timeout not in (None, socket._GLOBAL_DEFAULT_TIMEOUT):
                float_to_str = lambda f: ("%.4f" % f).rstrip('0').rstrip('.')
                timeout_str = 'timeout=%ss' % float_to_str(timeout)
                optional.append(timeout_str)
            if self.source_address:
                source_host, source_port = self.source_address
                shost_str = source_host or '<default>'
                sport_str = source_port or '<default>'
                source_str = 'source address=%s:%s' % (shost_str, sport_str)
                optional.append(source_str)
            if optional:
                optional_str = ' (%s)' % (', '.join(optional))
                log_tmpl += optional_str
            self.smtp_log.debug(log_tmpl, {'host': host, 'port': port})
        with disable_debug(self):
            return super(SMTPClient, self)._get_socket(host, port, timeout)

    def data(self, msg):
        filter_ = lambda r: r.msg.startswith('data:')
        with filter_log_traces(self, filter_):
            return super(SMTPClient, self).data(msg)

    def send(self, s):
        if self.smtp_log:
            if isinstance(s, bytes):
                for line_bytes in re.split(b'\r?\n', s.rstrip(bCRLF)):
                    if line_bytes:
                        line_bytes_repr = repr(line_bytes)
                        cmd_str = _bytes_repr_to_str(line_bytes_repr)
                        if cmd_str is None:
                            cmd_str = line_bytes_repr
                    else:
                        cmd_str = ''
                    self.smtp_log.debug('=> %s', cmd_str)
            else:
                cmd_str = s.rstrip(CRLF)
                self.smtp_log.debug('=> %s', cmd_str)
        with disable_debug(self):
            return super(SMTPClient, self).send(s)

    def getreply(self):
        # You might wonder why I'm not simply using "with disable_debug(...)"
        # like ".send()" does. Well, turns out ".getreply()" is more complicated
        # due to smtplib's multi-line response handling:
        # smtplib's ".getreply()" logs each line immediately when it is
        # received and string containing the complete (multi-line) reply at the
        # end.
        # I want to keep the immediate logging (so the log always contains the
        # complete conversation even if the connection was terminated at some
        # point) but get rid of the final log (which just duplicates the
        # information and I don't think anyone needs to debug multi-line reply
        # merging done by smtplib).
        filter_ = lambda r: r.msg.startswith('reply: retcode ')
        with filter_log_traces(self, filter_):
            return super(SMTPClient, self).getreply()


    def _print_debug(self, *args):
        if not self.smtp_log:
            return super(SMTPClient, self)._print_debug(*args)

        cmd = args[0]
        # no need to handle "send:" here as ".send()" disables debug printing
        # and logs explicitly.
        if cmd == 'reply:':
            prefix = '<= '
        else:
            prefix = cmd

        params = args[1:]
        params_str = None
        first_param = params[0] if (len(params) == 1) else None
        if isinstance(first_param, str):
            params_str = _bytes_repr_to_str(first_param)
        if params_str is None:
            # fallback, should be rarely used
            params_str = ' '.join(map(str, args[1:]))

        self.smtp_log.debug(prefix + params_str)


def _bytes_repr_to_str(value):
    # A common pattern in smtplib is
    #   self._print_debug('reply:', repr(line))
    #
    # This means we get the "repr()" output of a bytes instance which
    # does not look that nice:
    #   b'220 server.example ESMTP ...\r\n'
    # The regex below strips »b'« and »\r\n'« so the string (usually)
    # looks much nicer.
    #
    # This was done so I could keep the code changes to our internal
    # copy of "smtplib" as small as possible. Hopefully this eases
    # upgrades of "smtplib".
    match = _bytes_repr_regex.search(value)
    params_str = None
    if match:
        params_str = match.group(1)
    return params_str

@contextmanager
def disable_debug(smtp_instance):
    previous = smtp_instance.debuglevel
    smtp_instance.debuglevel = 0
    yield
    smtp_instance.debuglevel = previous

@contextmanager
def filter_log_traces(smtp_instance, filter_):
    previous_logger = smtp_instance.smtp_log
    if previous_logger:
        smtp_instance.smtp_log = FilteringWrapper(filter_, previous_logger)
    yield
    smtp_instance.smtp_log = previous_logger


_CRLF_STR = '\\\\r\\\\n'
_bytes_repr_regex = re.compile("^b?'(.+?)(?:%s)?'" % _CRLF_STR)

class FilteringWrapper(logging.Logger):
    def __init__(self, filter_, proxied_logger):
        logger_name = proxied_logger.name
        super(FilteringWrapper, self).__init__(logger_name)
        self._filter = filter_
        self._proxied_logger = proxied_logger

    def callHandlers(self, record):
        if self._filter(record):
            return
        self._proxied_logger.callHandlers(record)
