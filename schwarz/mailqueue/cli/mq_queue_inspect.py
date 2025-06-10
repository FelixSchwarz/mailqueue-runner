"""
mq-queue-inspect

Kommandozeilentool zum Inspizieren der Mailqueue (zeigt Nachrichten und Metadaten).

Usage:
    mq-queue-inspect [options]

Options:
  -C, --config=<CFG>    Pfad zur Konfigurationsdatei
  --queue-dir=<DIR>     Pfad zum Mailqueue-Verzeichnis (überschreibt Konfiguration)
  --verbose, -v         Ausführlichere Programmausgabe
"""

import sys
from argparse import ArgumentParser
from pathlib import Path

from schwarz.mailqueue.app_helpers import guess_config_path, init_app
from schwarz.mailqueue.queue_runner import MaildirBackedMsg, assemble_queue_with_new_messages


def mq_queue_inspect_main(argv=sys.argv):
    parser = ArgumentParser(description="Mailqueue inspizieren: Zeigt alle Nachrichten und Metadaten.")
    parser.add_argument('-C', '--config', help='Pfad zur Konfigurationsdatei')
    parser.add_argument('--queue-dir', help='Pfad zum Mailqueue-Verzeichnis (überschreibt Konfiguration)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Ausführlichere Programmausgabe')
    args = parser.parse_args(argv[1:])

    config_path = guess_config_path(args.config)
    settings = init_app(config_path, options={'verbose': args.verbose, 'quiet': not args.verbose})
    queue_dir = args.queue_dir or settings.get('queue_dir')
    if not queue_dir:
        sys.stderr.write('Kein queue_dir angegeben (weder in Konfiguration noch als Parameter).\n')
        sys.exit(2)

    # Nachrichten aus "new" und "cur" anzeigen
    for folder in ("new", "cur"):
        print(f"\nNachrichten in '{folder}':")
        queue = assemble_queue_with_new_messages(queue_dir, log=None) if folder == "new" else _assemble_queue(queue_dir, folder)
        if queue.qsize() == 0:
            print("  (keine Nachrichten)")
            continue
        while not queue.empty():
            msg_path = queue.get()
            try:
                msg = MaildirBackedMsg(msg_path)
                print(f"- Datei: {Path(msg_path).name}")
                print(f"  From: {msg.from_addr}")
                print(f"  To: {', '.join(msg.to_addrs)}")
                print(f"  Date: {msg.queue_date}")
                print(f"  Message-ID: {msg.msg_id}")
                print(f"  Retries: {msg.retries}")
                print(f"  Last Attempt: {msg.last_delivery_attempt}")
            except Exception as e:
                print(f"  Fehler beim Lesen von {msg_path}: {e}")


def _assemble_queue(queue_basedir, folder):
    import queue as pyqueue
    from schwarz.mailqueue.maildir_utils import find_messages
    q = pyqueue.Queue()
    for path in find_messages(queue_basedir, log=None, queue_folder=folder):
        q.put(path)
    return q


if __name__ == '__main__':
    mq_queue_inspect_main()
