
## mailqueue-runner

Queuing system to send email messages to a SMTP server. Its main feature is
to handle (temporary) errors when sending the message (e.g. interrupted network
connection) and detailed error logging.

To achieve that all messages are stored in a maildir-like queue before an
external helper script picks them up and delivery them to a "real" SMTP server.
The helper script must be called regularly (e.g. via cron).


### Motivation / related software

Many Web applications need to send emails. Usually this works by delivering the
message to a real SMTP server. All is fine until that SMTP server is not
reachable (e.g. network errors) or does not accept the message due to temporary
errors (e.g. DNS failure, unable to verify the sender).
This codes implements a (persistent) message queue and provides a script which
help sending emails reliably (assuming you have sufficiently free disk space).

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



## Non-goals

 - No code to actually generate an email (e.g. from a template, add attachments, ...)
 - Not suited for high volume message sending as every message is stored on
   the (slow) file system. I aim for maybe 100 messages per minute but if you
   want to go way higher you need to 


### License

The code is licensed unter the MIT license with only few exceptions: It
contains a custom (slightly modified) version of Python's smtplib which is
licensed under the [Python License 2.0](https://spdx.org/licenses/Python-2.0.html).


