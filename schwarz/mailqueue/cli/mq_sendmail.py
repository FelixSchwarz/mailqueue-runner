"""
mq-sendmail

Usage:
    mq-sendmail [options] [<recipients>...]

<recipients> is only optional when "-t" is used and the message contains at
least one email address in the "To", "CC" or "BCC" header.

Options:
  --aliases=<ALIAS_FN>  Path to aliases file
  -C, --config=<CFG>    Path to the config file
  -f, --from=address    Set envelope from address
  --set-date-header     Add a "Date" header to the message (if not present)
  --set-from-header     Add "From:" header to the message (if not present)
  --set-msgid-header    Add a "Message-ID" header to the message (if not present)
  --set-to-header       Add a "To" header to the message (if not present)
  -t, --read-recipients   Read additional recipients from the message
  --verbose, -v         More verbose program output

For compatibility with the traditional "sendmail" command as used by cronie,
some other flags are accepted but have no effect.
"""

import email.utils
import sys
import textwrap
from argparse import ArgumentParser
from email.parser import BytesHeaderParser
from typing import Sequence

from docopt import printable_usage

from schwarz.mailqueue.aliases_parser import _parse_aliases, lookup_adresses
from schwarz.mailqueue.app_helpers import guess_config_path, init_app, init_smtp_mailer
from schwarz.mailqueue.message_handler import InMemoryMsg, MessageHandler
from schwarz.mailqueue.message_utils import autogenerate_headers
from schwarz.mailqueue.queue_runner import MaildirBackend


__all__ = ['mq_sendmail_main']

def mq_sendmail_main(argv=sys.argv, return_rc_code=False):
    arguments = _parse_cli_parameters(argv)
    config_path = guess_config_path(arguments['--config'])
    recipient_params = arguments['<recipients>']
    verbose = arguments['--verbose']

    aliases_fn = arguments['--aliases']
    envelope_from = arguments['--from']
    set_date_header = arguments['--set-date-header']
    set_from_header = arguments['--set-from-header']
    set_msgid_header = arguments['--set-msgid-header']
    set_to_header = arguments['--set-to-header']
    read_recipients = arguments['--read-recipients']

    if not recipient_params and not read_recipients:
        usage_str = printable_usage(__doc__)
        sys.stdout.write(usage_str + '\n')
        sys.stderr.write('At least one recipient address is required.\n')
        sys.exit(2)

    msg_bytes = sys.stdin.buffer.read()
    input_headers = BytesHeaderParser().parsebytes(msg_bytes)
    if read_recipients:
        msg_recipients = _recipients_from_message(input_headers)
    else:
        msg_recipients = None
    aliases = _parse_aliases(aliases_fn) if aliases_fn else None
    recipients = lookup_adresses(recipient_params, aliases, msg_recipients=msg_recipients)
    if not recipients:
        sys.stderr.write('No recipient addresses found in message.\n')
        sys.exit(2)

    cli_options = {
        'verbose': verbose,
        'quiet'  : not verbose,
    }
    settings = init_app(config_path, options=cli_options)
    if envelope_from:
        from_addresses = lookup_adresses([envelope_from], aliases)
        msg_sender = from_addresses[0] if from_addresses else envelope_from
    else:
        msg_sender = settings.get('from')
    if not msg_sender:
        sys.stderr.write('No envelope sender address given (use "--from=...").\n')
        sys.exit(81)

    extra_header_lines = autogenerate_headers(
        input_headers,
        set_date_header,
        set_from_header,
        set_msgid_header,
        set_to_header,
        msg_sender,
        recipients,
    )
    msg = InMemoryMsg(msg_sender, recipients, extra_header_lines + msg_bytes)

    transports = [init_smtp_mailer(settings)]
    queue_dir = settings.get('queue_dir')
    if queue_dir:
        transports.append(MaildirBackend(queue_dir))
    mh = MessageHandler(transports=transports)
    send_result = mh.send_message(msg)

    if verbose:
        cli_output = build_cli_output(send_result)
        print(cli_output)
    was_sent = bool(send_result)
    exit_code = 0 if was_sent else 100
    if return_rc_code:
        return exit_code
    sys.exit(exit_code)


def _parse_cli_parameters(argv):
    # docopt (and docopt-ng) do not support long option names starting with
    # a singe dash: https://github.com/jazzband/docopt-ng/issues/69
    # arguments = docopt(__doc__, argv=argv[1:])

    tool_description = textwrap.dedent('''
        Command line tool to send an email message.
        The CLI parameters are a (extremly limited) subset of the Unix
        "sendmail" command sufficient to accept messages from cron daemons
        like cronie.
    ''').strip()
    parser = ArgumentParser(description=tool_description)

    # Remember to keep the argument specification in sync with the docstring.
    # The docstring is only used in case neither a recipient nor "-t" was given.
    parser.add_argument('recipients', nargs='*', help='recipient address(es) of the message')

    parser.add_argument('--aliases', help='Path to aliases file')
    parser.add_argument('-C', '--config', help='Path to the config file')
    parser.add_argument('-f', '--from', help='Set envelope from address')
    parser.add_argument('-t', '--read-recipients',
        action='store_true',
        help='Read additional recipients from the message')

    parser.add_argument('--set-date-header',
        action='store_true',
        help='Add a "Date" header to the message (if not present)')
    parser.add_argument('--set-from-header',
        action='store_true',
        help='Add "From:" header to the message (if not present)')
    parser.add_argument('--set-msgid-header',
        action='store_true',
        help='Add a "Message-ID" header to the message (if not present)')
    parser.add_argument('--set-to-header',
        action='store_true',
        help='Add a "To" header to the message (if not present)')

    parser.add_argument('--verbose', '-v',
        action='store_true',
        help='More verbose program output')

    # compatibility for cronie calls
    parser.add_argument('-F',
        help='sendmail compatibility: ...')
    parser.add_argument('-i',
        action='store_true',
        help='sendmail compatibility, no effect in mq-sendmail')
    parser.add_argument('-odi',
        action='store_true',
        help='sendmail compatibility: synchronous delivery (always on)')
    parser.add_argument('-oem',
        action='store_true',
        help='sendmail compatibility, no effect in mq-sendmail')
    parser.add_argument('-oi',
        action='store_true',
        help='sendmail compatibility, no effect in mq-sendmail')

    arguments = parser.parse_args(args=argv[1:])
    return {
        '--aliases'         : arguments.aliases,
        '--config'          : arguments.config,
        '--from'            : arguments.__dict__['from'],
        '--read-recipients' : arguments.read_recipients,
        '--set-date-header' : arguments.set_date_header,
        '--set-from-header' : arguments.set_from_header,
        '--set-msgid-header': arguments.set_msgid_header,
        '--set-to-header'   : arguments.set_to_header,
        '--verbose'         : arguments.verbose,
        '<recipients>'      : arguments.recipients,
    }


def _recipients_from_message(input_headers) -> Sequence[str]:
    recipients = set()
    for header in {'To', 'CC', 'BCC'}:
        header_lines = input_headers.get_all(header)
        if header_lines is None:
            continue
        for (_, recipient_addr) in email.utils.getaddresses(header_lines):
            recipients.add(recipient_addr)
    return tuple(recipients)



def build_cli_output(send_result) -> str:
    was_sent = bool(send_result)
    if was_sent:
        if send_result.queued:
            verb = 'queued'
            via = f' via {send_result.transport}'
        elif send_result.discarded:
            verb = 'discarded'
            via = ''
        else:
            verb = 'sent'
            via = f' via {send_result.transport}'
        return f'Message was {verb}{via}.'
    return ''
