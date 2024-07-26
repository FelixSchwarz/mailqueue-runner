# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import sys

import docopt

from ..mailflow_check import send_test_message


__all__ = [
    'send_test_message_main',
]

def send_test_message_main(argv=sys.argv, return_rc_code=False):
    """mq-send-test.

    Send a test message to ensure all SMTP credentials are correct.

    Usage:
        mq-send-test [options] <config> --to=EMAIL

    Options:
        --verbose -v    more verbose program output
        --quiet         suppress (most) logging
        --from=FROM     sender email address
    """
    arguments = docopt.docopt(send_test_message_main.__doc__, argv=argv[1:])
    config_path = arguments['<config>']
    cli_options = {
        'verbose': arguments['--verbose'],
        'recipient': arguments['--to'],
        'sender': arguments['--from'],
        'quiet'    : arguments['--quiet'],
    }
    was_sent = send_test_message(config_path, cli_options)
    exit_code = 0 if was_sent else 100
    if return_rc_code:
        return exit_code
    sys.exit(exit_code)
