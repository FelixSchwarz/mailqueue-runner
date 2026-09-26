# SPDX-License-Identifier: MIT

import sys
from argparse import ArgumentParser

from ..app_helpers import guess_config_path, parse_config
from ..queue_runner import one_shot_queue_run


__all__ = [
    'one_shot_queue_run_main',
]

def one_shot_queue_run_main(argv=sys.argv, return_rc_code=False):
    """mq-run.

    Try to deliver all messages in the queue directory.

    Usage:
        mq-run [options] [<queue_dir>]

    Options:
        -C, --config=<CFG>  Path to the config file
        --verbose -v        more verbose program output
    """
    arguments = _parse_cli_parameters(argv)
    config_path = guess_config_path(arguments.config)
    queue_dir = arguments.queue_dir

    if not queue_dir:
        settings = parse_config(config_path, section_name='mqrunner')
        queue_dir = settings.get('queue_dir')
    if not queue_dir:
        sys.stderr.write('No queue directory specified\n')
        return 10 if return_rc_code else sys.exit(10)

    cli_options = {
        'verbose': arguments.verbose,
    }
    one_shot_queue_run(queue_dir, config_path, options=cli_options)
    exit_code = 0
    return exit_code if return_rc_code else sys.exit(exit_code)


def _parse_cli_parameters(argv):
    # Remember to keep the argument specification in sync with the docstring
    # of `one_shot_queue_run_main()`.
    parser = ArgumentParser(
        prog='mq-run',
        description='Try to deliver all messages in the queue directory.',
    )
    parser.add_argument('queue_dir', nargs='?', help='path to the queue directory')
    parser.add_argument('-C', '--config', metavar='CFG', help='Path to the config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='more verbose program output')
    return parser.parse_args(args=argv[1:])
