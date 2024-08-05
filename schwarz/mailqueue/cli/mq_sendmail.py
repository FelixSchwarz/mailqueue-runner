"""
mq-sendmail

Usage:
    mq-sendmail [options] <recipients>...

Options:
  --aliases=<ALIAS_FN>  Path to aliases file
  -C, --config=<CFG>    Path to the config file
  -f, --from=address    set envelope from address
  --set-date-header     Add a "Date" header to the message (if not present)
  --set-from-header     Add "From:" header to the message (if not present)
  --set-msgid-header    Add a "Message-ID" header to the message (if not present)
  --set-to-header       add a "To" header to the message (if not present)
  --verbose, -v         more verbose program output
"""

import sys
from datetime import datetime as DateTime, timezone
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.utils import format_datetime, make_msgid
from io import BytesIO

from docopt import docopt

from schwarz.mailqueue.aliases_parser import _parse_aliases, lookup_adresses
from schwarz.mailqueue.app_helpers import guess_config_path, init_app, init_smtp_mailer
from schwarz.mailqueue.message_handler import InMemoryMsg, MessageHandler
from schwarz.mailqueue.queue_runner import MaildirBackend


__all__ = ['mq_sendmail_main']

def mq_sendmail_main(argv=sys.argv, return_rc_code=False):
    arguments = docopt(__doc__, argv=argv[1:])
    config_path = guess_config_path(arguments['--config'])
    recipient_params = arguments['<recipients>']
    verbose = arguments['--verbose']

    aliases_fn = arguments['--aliases']
    envelope_from = arguments['--from']
    set_date_header = arguments['--set-date-header']
    set_from_header = arguments['--set-from-header']
    set_msgid_header = arguments['--set-msgid-header']
    set_to_header = arguments['--set-to-header']

    aliases = _parse_aliases(aliases_fn) if aliases_fn else None
    recipients = lookup_adresses(recipient_params, aliases)

    msg_bytes = sys.stdin.buffer.read()
    cli_options = {
        'verbose': verbose,
        'quiet'  : not verbose,
    }
    settings = init_app(config_path, options=cli_options)
    if envelope_from:
        msg_sender = envelope_from
    else:
        msg_sender = settings.get('from')
    if not msg_sender:
        sys.stderr.write('No envelope sender address given (use "--from=...").\n')
        sys.exit(81)

    extra_header_lines = autogenerated_headers(
        set_date_header,
        set_from_header,
        set_msgid_header,
        set_to_header,
        msg_bytes,
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


def autogenerated_headers(
        set_date_header, set_from_header, set_msgid_header,
        set_to_header,
        msg_bytes,
        msg_sender,
        recipients,
    ) -> bytes:
    input_headers = BytesHeaderParser().parse(BytesIO(msg_bytes))
    extra_headers = EmailMessage()
    input_msg_date = input_headers.get('Date')
    if set_date_header and not input_msg_date:
        extra_headers['Date'] = format_datetime(DateTime.now(timezone.utc))
    input_msg_from = input_headers.get('From')
    if set_from_header and not input_msg_from:
        extra_headers['From'] = msg_sender
    input_msg_to = input_headers.get('To')
    if set_to_header and (not input_msg_to) and recipients:
        extra_headers['To'] = ', '.join(recipients)
    input_msg_id = input_headers.get('Message-ID')
    if set_msgid_header and not input_msg_id:
        _, smtp_sender_domain = msg_sender.split('@', 1)
        extra_headers['Message-ID'] = make_msgid(domain=smtp_sender_domain)

    prepended_header_lines = b''
    if extra_headers:
        fake_msg_bytes = extra_headers.as_bytes()
        prepended_header_lines = fake_msg_bytes.split(b'\n\n', 1)[0] + b'\n'
    return prepended_header_lines


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
