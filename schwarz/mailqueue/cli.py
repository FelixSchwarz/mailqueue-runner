# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import docopt

from .queue_runner import one_shot_queue_run


__all__ = [
    'one_shot_queue_run_main',
]

def one_shot_queue_run_main():
    """mq-run.

    Usage:
        mq-run [options] <config> <queue_dir>

    Options:
        --verbose -v    more verbose program output
    """
    arguments = docopt.docopt(one_shot_queue_run_main.__doc__)
    config_path = arguments['<config>']
    queue_dir = arguments['<queue_dir>']
    cli_options = {
        'verbose': arguments['--verbose'],
    }
    one_shot_queue_run(queue_dir, config_path, options=cli_options)

