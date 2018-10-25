# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Python-2.0 or MIT
# The code in this file heavily relies on Python's smtplib so I guess licensing
# it under "Python License 2.0" is in order. However my own contributions
# can also be used under the MIT license.

from __future__ import absolute_import, print_function, unicode_literals

from .lib.smtplib_py37 import (
    _fix_eols,
    SMTP,
    SMTPDataError,
    SMTPRecipientsRefused,
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
    # ,------------------------------------------------------------------------
    # copied from "smtplib" shipped with Python 3.7
    # modified to raise SMTPRecipientRefused when ANY recipient was rejected
    # License: Python-2.0 (my changes: public domain or CC-0 - your choice)
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
        if isinstance(to_addrs, str):
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

