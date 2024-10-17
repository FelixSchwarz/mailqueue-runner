# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import sys


try:
    import colorama
    has_colorama = True
except ImportError:
    has_colorama = False
import docopt

from ..app_helpers import guess_config_path
from ..mailflow_check import send_test_message


__all__ = [
    'send_test_message_main',
]

def send_test_message_main(argv=sys.argv, return_rc_code=False):
    """mq-send-test.

    Send a test message to ensure all SMTP credentials are correct.

    Usage:
        mq-send-test [options] --to=EMAIL

    Options:
        -C, --config=<CFG>  Path to the config file
        --quiet         suppress (most) logging
        --from=FROM     sender email address
        --verbose -v        more verbose program output
    """
    arguments = docopt.docopt(send_test_message_main.__doc__, argv=argv[1:])
    verbose = arguments['--verbose']
    quiet = arguments['--quiet']
    recipient = arguments['--to']

    config_path = guess_config_path(arguments['--config'])
    cli_options = {
        'verbose': verbose,
        'recipient': recipient,
        'sender': arguments['--from'],
        'quiet': quiet,
    }
    was_sent = send_test_message(config_path, cli_options)
    exit_code = 0 if was_sent else 100
    if verbose or (not quiet and sys.stdout.isatty()):
        msg = _status_message(was_sent, recipient)
        print(msg)
    if return_rc_code:
        return exit_code
    sys.exit(exit_code)

def _status_message(was_sent, recipient) -> str:
    if has_colorama and sys.stdout.isatty():
        _cf_green = colorama.Fore.GREEN
        _cf_lightred = colorama.Fore.LIGHTRED_EX
        _cf_reset = colorama.Style.RESET_ALL
    else:
        _cf_green = ''
        _cf_lightred = ''
        _cf_reset = ''

    if was_sent:
        return f'{_cf_green}OK{_cf_reset}: message sent succesfully to {recipient}.'
    else:
        return f'{_cf_lightred}FAIL{_cf_reset}: message sending failed!'
