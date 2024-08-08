
## mailqueue-runner

This library provides a robust way to send email messages to an external SMTP
server. The API was designed for easy integration into your Python (web) application.

Additionally, there are CLI scripts (with a very limited feature set) to enable
applications to send email via CLI as done traditionally with `/usr/bin/sendmail`
and `/usr/bin/mail`. So for very simple use cases this software is also an
alternative to [msmtp](https://github.com/marlam/msmtp) and
[ssmtp](https://packages.qa.debian.org/s/ssmtp.html).

At the core the code contains a queuing system to handle (temporary) errors
when sending the message (e.g. interrupted network connection) and provides
detailed error logging.

When a message cannot be sent via SMTP it can be stored in a maildir-like queue
on disk. An external helper script (`mq-run`) picks them up at a later time and
tries to deliver these messages again. The helper script must be called
regularly (e.g. via cron).

As a nice bonus, the library is pretty modular so you can plug in custom code and
adapt the library to your needs.


### Installation

    $ pip install mailqueue-runner

If you are not interested in the Python integration and only want to use
`mq-sendmail`, you can use my [COPR repo for Fedora and RHEL](https://copr.fedorainfracloud.org/coprs/fschwarz/mailqueue-runner/):

    $ dnf copr enable fschwarz/mailqueue-runner
    $ dnf install mailqueue-runner


### Usage `mq-sendmail` (CLI)

The code provides a CLI application named `mq-sendmail` which provides (basic)
compatibility with the common Un*x `/usr/bin/sendmail` application. Additionally,
it supports some convenient parameters added by [msmtp](https://github.com/marlam/msmtp).

    $ mq-sendmail --set-date-header --set-msgid-header root <<<MAIL
    Subject: Test email
    From: me@site.example
    MIME-Version: 1.0
    Content-Transfer-Encoding: 8bit
    Content-Type: text/plain; charset=UTF-8

    mail body
    MAIL

By default, the configuration read from `~/.mailqueue-runner.conf` or
`/etc/mailqueue-runner.conf` though you can also specify the config file
explicitly using `--config=...`. Similar to other `sendmail` implementations,
the application parses `/etc/aliases` to look up the recipient's email address.

Please note that the code will only enqueue the message after a failed delivery
if the configuration file contains the `queue_dir` option.


### Usage `mq-mail` (CLI)

The code provides a CLI application named `mq-mail` which provides (basic)
compatibility with `/usr/bin/mail` application.

    $ mq-mail --from-address="me@site.example" --subject "subject" root <<<MAIL
    mail body
    MAIL

By default, the configuration read from `~/.mailqueue-runner.conf` or
`/etc/mailqueue-runner.conf` though you can also specify the config file
explicitly using `--config=...`. The application parses `/etc/aliases` to look
up the recipient's email address.

Please note that the code will only enqueue the message after a failed delivery
if the configuration file contains the `queue_dir` option.


### Configuration (CLI scripts)

The configuration file uses the traditional "ini"-like format:

    [mqrunner]
    smtp_hostname = hostname
    smtp_port = 587
    smtp_username = someuser@site.example
    smtp_password = secret
    # optional but the CLI scripts will not queue messages if this is not set
    queue_dir = /path/to/mailqueue
    # optional, SMTP envelope from (also used when "--set-from-header" is given)
    from = user@host.example
    # optional, format as described in
    # https://docs.python.org/3/library/logging.config.html#logging-config-fileformat
    logging_conf = /path/to/logging.conf

For more information about wrapping `mq-run` (e.g. to reuse an existing configuration format) please read [Cookbook: Custom wrapper for mq-run](#cookbook-custom-wrapper-for-mq-run).


### Usage (mail submission/Python integration)

```python
from schwarz.mailqueue import init_smtp_mailer, MaildirBackend, MessageHandler
# settings: a dict-like instance with keys as shown below in the "Configuration" section
settings = {}
# Adapt the list of transports as you like (ordering matters):
# - always enqueue: use "MaildirBackend()" only
# - never enqueue: use "init_smtp_mailer()" only
transports = [
    init_smtp_mailer(settings),
    MaildirBackend('/path/to/queue-dir'),
]
handler = MessageHandler(transports)
msg = b'…' # RFC-822/RFC-5322 message as bytes or email.Message instance
was_sent = handler.send_message(msg, sender='foo@site.example', recipient='bar@site.example')
# "was_sent" evaluates to True if the message was sent via SMTP or queued
# for later delivery.
was_queued = (getattr(send_result, 'queued', None) is not False)
```


### Usage (mq-run)

If you use queueing to handle temporary delivery problems, you need to run
a script periodically to retry delivery. `mq-run` provides that ability:

    $ mq-run

If you want to test your configuration you can send a test message to ensure
the mail flow is set up correctly:

    $ mq-send-test --to=recipient@site.example


### Logging

Logs can help you monitoring the mail processing. The library uses two separate
loggers depending on the type of delivery:

- `mailqueue.delivery_log`: message was delivered to the SMTP server
- `mailqueue.queue_log`: message was queued and will be delivered later by `mq-run`


### Plugins

The library allows customization of message handling via plugins. Plugins are built
with the [Puzzle Plugin System](https://github.com/FelixSchwarz/puzzle-plugin-system) ([blinker](https://github.com/jek/blinker)+setuptools).
Plugin support is optional and requires the additional `PuzzlePluginSystem`
dependency (`pip install mailqueue-runner[plugins]`).

Features which can be implemented by plugins:

- notification about successful/failed deliveries (e.g. additional logging, storing some data in external databases, ...)
- discarding queued messages after failed delivery attempts (e.g. give up after 10 failed attempts)

To learn more about plugin discovery/plugin development please head of to the [Puzzle Plugin project](https://github.com/FelixSchwarz/puzzle-plugin-system).


CLI tools like `mq-run` will load your plugin if it is added to the
extension point `mailqueue.plugins`, e.g.

```
# setup.cfg (of your custom app)
[options.entry_points]
mailqueue.plugins =
    myplugin = example.app.mqplugin
```

Example plugin code:

```python
# example/app/mqplugin.py
from schwarz.puzzle_plugins import connect_signals, disconnect_signals
from schwarz.mailqueue import registry, MQAction, MQSignal

class MyPlugin:
    def __init__(self, registry):
        self._connected_signals = None
        self._registry = registry

    def signal_map(self):
        return {
            MQSignal.delivery_successful: self.delivery_successful,
            MQSignal.delivery_failed: self.delivery_failed,
        }

    def delivery_successful(self, _, msg, send_result):
        # called when a message was delivered successfully
        pass

    def delivery_failed(self, _, msg, send_result):
        # called when message delivery failed
        if msg.retries > 10:
            # discard messsage after 10 failed delivery attempts
            return MQAction.DISCARD
        return None

def initialize(context, registry):
    plugin = MyPlugin(registry)
    plugin._connected_signals = connect_signals(plugin.signal_map(), registry)
    context['plugin'] = plugin

def terminate(context):
    plugin = context['plugin']
    disconnect_signals(plugin._connected_signals, plugin._registry)
    plugin._registry = None
    plugin._connected_signals = None
```


### Cookbook: Custom wrapper for mq-run

While `mq-run` usually works great, sometimes you might want more control. For example you might not want to duplicate your configuration (once for your actual application and once for `mq-run`). The good news is that you can write a pretty minimal wrapper to leverage your existing code without duplicating `mq-run`'s functionaliy:

```python
#!/usr/bin/env python3

from schwarz.mailqueue.queue_runner import one_shot_queue_run

def main():
    # set up custom configuration, logging here (use your existing code)
    cli_options = {'verbose': True}
    # prepare configuration as expected by mailqueue-runner
    settings = {
        # … (smtp settings)

        # --- optional ---
        # only load "myplugin" plugin
        'plugins': 'myplugin',
        # do not reset currently configured loggers, just add a few for UI output
        'basic_logging_configured': True,
        # ability to inject a custom MessageHandler instance for maximum flexibility
        #'mh': …
    }
    one_shot_queue_run(queue_dir, options=cli_options, settings=settings)

if __name__ == '__main__':
    main()
```


### Cookbook: Conservative Message Sending

The default configuration shown above tries to send messages via SMTP if possible and only serialize the data to persistent storage (filesystem) when the SMTP delivery failed. That approach is usually a good compromise between performance (serializing to disk is slow) while ensuring that messages will be sent eventually.

However sometimes it is really important that you never loose a single message even if mailqueue-runner has a bug and crashes directly after trying to send the message with SMTP. To mitigate this risk you can use mailqueue-runner to store the message persistently before even trying to send it via SMTP:

```python
from schwarz.mailqueue import enqueue_message, MessageHandler

md_msg = enqueue_message(msg, path_maildir,
    sender      = '...',
    recipients  = ('...',),
    in_progress = True,
    return_msg  = True,
)
handler = MessageHandler(transports=...)
was_sent = handler.send_message(md_msg, sender='foo@site.example', recipient='bar@site.example')
```

Please note that you don't have to use a single approach exclusively in your application. You can use conservative message sending as shown above for really important messages while relying on a performance-focussed approach for not-so-important majority of your messages.


### Motivation / related software

Many web applications need to send emails. Usually this works by delivering the
message to a real SMTP server which then distributes the messages to remote
mailservers all over the net (well, mostly Gmail these days ;-).
All is fine until your SMTP server is not reachable (e.g. network errors) or
does not accept the message due to temporary errors (e.g. DNS failure, unable
to verify the sender).

"mailqueue-runner" implements a (persistent) message queue and provides a
script which helps sending emails reliably (assuming you have sufficiently
free disk space).

[repoze.sendmail](https://github.com/repoze/repoze.sendmail) is similar and a
solid piece of software. I wrote yet another library because I wanted

 - avoid data loss if the SMTP server does not accept messages due to (temporary)
   errors without delaying messages while everything is working fine (i.e. most
   of the time)
 - avoid nasty surprises if the SMTP server rejects one (but not all) recipients
   in a message to multiple recipients
 - different error handling/better integration into custom web applications
   (delivery logs, error handling)
 - better error logging (including the ability to log the complete SMTP dialog)
 - only minimal modification to queued messages (repoze.sendmail uses Python's
   email module to manipulate message headers required for delivery)

[django-mail-queue](https://github.com/Privex/django-mail-queue) provides a Django app which also provides a web ui. Obviously restricted to Django and there is too much implicit ("magic") behavior for my taste. However I recommend trying this library if you are using Django.


### Non-goals

 - No code to actually generate an email (e.g. from a template, add attachments, ...)
 - Probably not suited for high volume message sending (>> 100 messages per second)
   when your SMTP server is not available as messages will be stored on the
   (slow) file system.


### Tested Python versions

The project uses GitHub Actions to run the test suite. Hopefully this means all
tested versions are suitable for production.
At the moment I test Python 3.6-3.12 as well as pypy3 on Linux.
Deployment on Windows is not recommended as all locking will be disabled on
Windows (due to its inability to delete/move open files) but development on
a Windows machine should be fine.


### License

The code is licensed unter the MIT license with only few exceptions: It
contains a custom (slightly modified) version of Python's smtplib which is
licensed under the [Python License 2.0](https://spdx.org/licenses/Python-2.0.html).
