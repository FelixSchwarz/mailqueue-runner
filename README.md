
## mailqueue-runner

This library helps sending email messages to an SMTP server. Its main feature
is a queuing system to handle (temporary) errors when sending the message
(e.g. interrupted network connection) and detailed error logging.

When a message can not be sent via SMTP it can be stored in a maildir-like queue
on disk. An external helper script (`mq-run`) picks them up at a later time and
tries to deliver these messages again. The helper script must be called
regularly (e.g. via cron).

As a nice bonus the library is pretty modular so you can plug in custom code and
adapt the library to your needs.

### Usage (mail submission)

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


### Usage (mq-run)

The `mq-run` script sends all queued messages to an SMTP server:

    mq-run /path/to/config.ini /path/to/queue

If you want to test your configuration you can send a test message to ensure
the mail flow is set up correctly:

    mq-send-test /path/to/config.ini /path/to/queue --to=recipient@site.example

### Configuration (mq-run)

The configuration file uses the traditional "ini"-like format:

    [mqrunner]
    smtp_hostname = hostname
    smtp_port = 587
    smtp_username = someuser@site.example
    smtp_password = secret
    # optional, format as described in
    # https://docs.python.org/3/library/logging.config.html#logging-config-fileformat
    logging_conf = /path/to/logging.conf

For more information about wrapping `mq-run` (e.g. to reuse an existing configuration format) please read [Cookbook: Custom wrapper for mq-run](#cookbook-custom-wrapper-for-mq-run).


### Logging

Logs can help you monitoring the mail processing. The library uses two separate
loggers depending on the type of delivery:

- `mailqueue.delivery_log`: message was delivered to the SMTP server
- `mailqueue.queue_log`: message was queued and will be delivered later by `mq-run`


### Plugins

The library allows customization of message handling via plugins. Plugins are built
with the [Puzzle Plugin System](https://github.com/FelixSchwarz/puzzle-plugin-system) ([blinker](https://github.com/jek/blinker)+setuptools).

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


### Non-goals

 - No code to actually generate an email (e.g. from a template, add attachments, ...)
 - Probably not suited for high volume message sending (>> 100 messages per second)
   when your SMTP server is not available as messages will be stored on the
   (slow) file system.


### Tested Python versions

I use [Travis](https://travis-ci.com/FelixSchwarz/mailqueue-runner) to run the
test suite. Hopefully this means all tested versions are suitable for production.
At the moment I test Python 2.7 and Python 3.6-3.8 as well as pypy3 on Linux.
Deployment on Windows is not recommended as all locking will be disabled on
Windows (due to its inability to delete/move open files) but development on
a Windows machine should be fine.


### License

The code is licensed unter the MIT license with only few exceptions: It
contains a custom (slightly modified) version of Python's smtplib which is
licensed under the [Python License 2.0](https://spdx.org/licenses/Python-2.0.html).


