"""
mq-mail

Command line tool to send an email message.
The CLI parameters are a (extremly limited) subset of the "mailx" command,
just so you can use the default settings for "command_email" in dnf automatic.

Usage:
    mq-mail [options] <recipient>

Options:
  -s, --subject=<SUBJECT>   specify subject of message to be sent
  -r, --from-address=<FROM> set source address used by MTAs

  --aliases=<ALIAS_FN>  Path to aliases file
  -C, --config=<CFG>    Path to the config file
  --verbose, -v         more verbose program output

  -Ssendwait            ignored (just for compatibility with mailx)
  -Snosendwait          ignored (just for compatibility with mailx)
"""

import email
import email.utils
import sys
import textwrap
from argparse import ArgumentParser

from schwarz.mailqueue.aliases_parser import _parse_aliases, lookup_adresses
from schwarz.mailqueue.app_helpers import guess_config_path, init_app, init_smtp_mailer
from schwarz.mailqueue.message_handler import InMemoryMsg, MessageHandler
from schwarz.mailqueue.message_utils import autogenerate_headers
from schwarz.mailqueue.queue_runner import MaildirBackend


__all__ = ['mq_mail_main']

def mq_mail_main(argv=sys.argv, return_rc_code=False):
    arguments = _parse_cli_parameters(argv)
    config_path = guess_config_path(arguments['--config'])

    aliases_fn = arguments['--aliases']
    envelope_from = arguments['--from-address']
    subject = arguments['--subject']
    verbose = arguments['--verbose']
    recipient_param = arguments['<recipient>']

    aliases = _parse_aliases(aliases_fn) if aliases_fn else None
    recipients = lookup_adresses([recipient_param], aliases) or [recipient_param]

    msg_body = sys.stdin.buffer.read()
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
        sys.stderr.write('No sender address given (use "--from-address=...").\n')
        sys.exit(81)

    stub_msg = email.message_from_bytes(msg_body)
    stub_msg['MIME-Version'] = '1.0'
    stub_msg['Content-Transfer-Encoding'] = '8bit'
    stub_msg['Content-Type'] = 'text/plain; charset="UTF-8"'
    if subject:
        stub_msg['Subject'] = subject

    extra_header_lines = autogenerate_headers(
        input_headers=stub_msg,
        set_date_header=True,
        set_from_header=True,
        set_msgid_header=True,
        set_to_header=True,
        msg_sender=msg_sender,
        recipients=recipients,
    )
    msg_bytes = extra_header_lines + stub_msg.as_bytes()
    msg = InMemoryMsg(msg_sender, recipients, msg_bytes)

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
        The CLI parameters are a (extremly limited) subset of the "mailx" command,
        just so you can use the default settings for "command_email" in dnf automatic.
    ''').strip()
    parser = ArgumentParser(description=tool_description)

    parser.add_argument('recipient', help='recipient of the message')

    parser.add_argument('-s', '--subject', help='specify subject of message to be sent')
    parser.add_argument('-r', '--from-address', help='set source address used by MTAs')
    parser.add_argument('--aliases', help='Path to aliases file')
    parser.add_argument('-C', '--config', help='Path to the config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='more verbose program output')

    sendwait_group = parser.add_mutually_exclusive_group()
    sendwait_group.add_argument(
        '-Ssendwait',
        action='store_true',
        help='ignored (just for compatibility with mailx)',
    )
    sendwait_group.add_argument(
        '-Snosendwait',
        action='store_true',
        help='ignored (just for compatibility with mailx)',
    )

    arguments = parser.parse_args(args=argv[1:])
    return {
        '--aliases'    : arguments.aliases,
        '--config'     : arguments.config,
        '--from-address': arguments.from_address,
        '--subject'    : arguments.subject,
        '--verbose'    : arguments.verbose,
        '<recipient>'  : arguments.recipient
    }


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
