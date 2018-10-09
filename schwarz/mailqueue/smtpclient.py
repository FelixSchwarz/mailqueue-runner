# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Python-2.0
# The code in this file heavily relies on Python's smtplib so I guess licensing
# it under "Python License 2.0" is in order. However my own contributions
# can also be used under the MIT license.

from __future__ import absolute_import, print_function, unicode_literals

from .lib.smtplib_py37 import (
    _fix_eols,
    SMTP,
    SMTPDataError,
    SMTPRecipientsRefused,
    SMTPSenderRefused
)


__all__ = ['SMTPClient']


class SMTPClient(SMTP):
    # ,------------------------------------------------------------------------
    # copied from "smtplib" shipped with Python 3.7
    # License: Python-2.0
    def sendmail(self, from_addr, to_addrs, msg, mail_options=[], rcpt_options=[]):
        self.ehlo_or_helo_if_needed()
        esmtp_opts = []
        if isinstance(msg, str):
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
        senderrs = {}
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]
        for each in to_addrs:
            (code, resp) = self.rcpt(each, rcpt_options)
            if (code != 250) and (code != 251):
                senderrs[each] = (code, resp)
            if code == 421:
                self.close()
                raise SMTPRecipientsRefused(senderrs)
        if len(senderrs) == len(to_addrs):
            # the server refused all our recipients
            self._rset()
            raise SMTPRecipientsRefused(senderrs)
        (code, resp) = self.data(msg)
        if code != 250:
            if code == 421:
                self.close()
            else:
                self._rset()
            raise SMTPDataError(code, resp)
        #if we got here then somebody got our mail
        return senderrs
    # `------------------------------------------------------------------------

