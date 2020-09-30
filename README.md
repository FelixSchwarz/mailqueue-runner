
## mailqueue-runner

Queuing system to send email messages to an SMTP server. Its main feature is
to handle (temporary) errors when sending the message (e.g. interrupted network
connection) and detailed error logging.

To achieve that all messages are stored in a maildir-like queue before an
external helper script picks them up and delivery them to a "real" SMTP server.
The helper script must be called regularly (e.g. via cron).


### Usage

The `mq-run` script sends all queued messages to an SMTP server:

    mq-run /path/to/config.ini /path/to/queue

If you want to test your configuration you can send a test message to ensure
the mail flow is set up correctly:

    mq-send-test /path/to/config.ini /path/to/queue --to=recipient@site.example

### Configuration

The configuration file uses the traditional "ini"-like format:

    [mqrunner]
    smtp_hostname = hostname
    smtp_port = 587
    smtp_username = someuser@site.example
    smtp_password = secret


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

 - better error logging (including the ability to log the complete SMTP dialog)
 - avoid data loss if the SMTP server rejects one (but not all) recipients
   in a message to multiple recipients
 - different error handling/better integration into custom web applications
   (delivery logs, error handling)
 - only minimal modification to queued messages (repoze.sendmail uses Python's
   email module to manipulate message headers required for delivery)
 - a daemon with near-realtime message sending to avoid unnecessary delays



### Non-goals

 - No code to actually generate an email (e.g. from a template, add attachments, ...)
 - Not suited for high volume message sending as every message is stored on
   the (slow) file system. I aim for maybe 100 messages per minute but if you
   want to go way higher you'll need to find a different solution (see issue #5).


### Tested Python versions

I use [Travis](https://travis-ci.com/FelixSchwarz/mailqueue-runner) to run the
test suite. Hopefully this means all tested versions are suitable for production.
At the moment I test Python 2.7 and Python 3.6/3.7 on Linux.
Deployment on Windows is not recommended as all locking will be disabled on
Windows (due to its inability to delete/move open files) but development on
a Windows machine should be fine.


### License

The code is licensed unter the MIT license with only few exceptions: It
contains a custom (slightly modified) version of Python's smtplib which is
licensed under the [Python License 2.0](https://spdx.org/licenses/Python-2.0.html).


