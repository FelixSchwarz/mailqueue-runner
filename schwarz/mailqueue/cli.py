# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import sys

import docopt

from .mailflow_check import send_test_message
from .queue_runner import one_shot_queue_run


__all__ = [
    'one_shot_queue_run_main',
    'send_test_message_main',
]

def one_shot_queue_run_main(argv=sys.argv, return_rc_code=False):
    """mq-run.

    Usage:
        mq-run [options] <config> <queue_dir>

    Options:
        --verbose -v    more verbose program output
    """
    arguments = docopt.docopt(one_shot_queue_run_main.__doc__, argv=argv[1:])
    config_path = arguments['<config>']
    queue_dir = arguments['<queue_dir>']
    cli_options = {
        'verbose': arguments['--verbose'],
    }
    one_shot_queue_run(queue_dir, config_path, options=cli_options)
    exit_code = 0
    return exit_code if (return_rc_code) else sys.exit(exit_code)


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

