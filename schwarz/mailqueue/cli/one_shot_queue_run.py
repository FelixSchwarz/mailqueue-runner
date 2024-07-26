# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import sys

import docopt

from ..queue_runner import one_shot_queue_run


__all__ = [
    'one_shot_queue_run_main',
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
