# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from __future__ import absolute_import, print_function, unicode_literals

import logging
import logging.config
import os
import sys

from schwarz.puzzle_plugins import parse_list_str, PluginLoader

from .compat import configparser
from .mailer import SMTPMailer
from .plugins import registry


__all__ = [
    'init_app',
    'init_smtp_mailer',
]

# tests can override the working set to test plugin functionality
_working_set = None

def init_app(config_path, options=None, settings=None):
    assert (config_path is not None) ^ (settings is not None)
    if settings is None:
        settings = parse_config(config_path, section_name='mqrunner')
    configure_logging(settings, options or {})

    log = logging.getLogger('mailqueue')
    enabled_plugins = parse_list_str(settings.get('plugins', '*'))
    plugin_loader = PluginLoader(
        'mailqueue.plugins',
        enabled_plugins = enabled_plugins,
        working_set     = _working_set,
        log             = log,
    )
    plugin_loader.initialize_plugins(registry)
    settings['plugin_loader'] = plugin_loader

    return settings


def init_smtp_mailer(settings, smtp_log=None):
    smtp_settings = _subdict(settings, prefix='smtp_')
    if 'hostname' not in smtp_settings:
        log = logging.getLogger('mailqueue')
        log.error('No SMTP host configured ("smtp_hostname = ...")')
        sys.exit(30)
    smtp_settings['smtp_log'] = smtp_log or logging.getLogger('mailqueue.smtp')
    mailer = SMTPMailer(**smtp_settings)
    return mailer

def _subdict(d, prefix):
    subdict = {}
    for key, value in d.items():
        if key.startswith(prefix):
            plain_key = key[len(prefix):]
            subdict[plain_key] = value
    return subdict


def _no_section_headers(e):
    return isinstance(e, configparser.MissingSectionHeaderError)

def _contains_duplicate_section(e):
    return isinstance(e, configparser.DuplicateSectionError)

def _contains_duplicate_option(e):
    # ConfigParser in Python 2 raises an Exception for duplicate options so
    # we don't have to care about the missing "DuplicateOptionError".
    return isinstance(e, configparser.DuplicateOptionError)


def parse_config(config_path, section_name=None):
    filename = os.path.basename(config_path)
    if not os.path.exists(config_path):
        sys.stderr.write('config file "%s" not found.\n' % filename)
        sys.exit(20)

    parser = configparser.SafeConfigParser()
    exc_msg = None
    try:
        parser.read(config_path)
        # ConfigParser in Python 2 has no ".items()" (without parameters)
        sections = (section_name, ) if section_name else parser.sections()
        for section in sections:
            parser.items(section)
    except configparser.Error as e:
        line_detail = ''
        if hasattr(e, 'errors') and len(e.errors) > 0:
            line_nr, line_str = e.errors[0]
            line_detail = ' (line %d: "%s")' % (line_nr, line_str)
        if _no_section_headers(e):
            exc_msg = 'no section headers found: "[section]"'
        elif _contains_duplicate_section(e):
            exc_msg = 'duplicate section [%s]' % e.section
            line_detail = ' (line %d)' % e.lineno
        elif _contains_duplicate_option(e):
            exc_msg = 'duplicate option "%s" in [%s]' % (e.option, e.section)
            line_detail = ' (line %d)' % e.lineno
        else:
            exc_msg = 'invalid line'
        exc_msg = exc_msg + line_detail
    if exc_msg is not None:
        error_msg = 'File "%s" is not a valid config file:' % filename
        sys.stderr.write(error_msg + '\n')
        sys.stderr.write(exc_msg + '\n')
        sys.exit(21)

    if section_name:
        try:
            settings_mqrunner = parser.items(section_name)
        except configparser.NoSectionError:
            exc_msg = 'File "%s" has no section "[%s]"' % (filename, section_name)
            sys.stderr.write(exc_msg + '\n')
            sys.exit(22)
        return dict(settings_mqrunner)
    return parser


def configure_logging(settings, options):
    log_path = settings.get('logging_config')
    basic_logging_configured = settings.get('basic_logging_configured', False)
    if log_path:
        if not os.path.exists(log_path):
            sys.stderr.write('No log configuration file "%s".\n' % log_path)
            sys.exit(25)
        try:
            logging.config.fileConfig(log_path)
        except Exception as e:
            sys.stderr.write('Malformed logging configuration file "%s": %s\n' % (log_path, e))
            sys.exit(26)
    elif not basic_logging_configured:
        logging.basicConfig()

    verbose = options.get('verbose')
    quiet = options.get('quiet')
    assert not (verbose and quiet)

    if verbose:
        ui_logging = logging.DEBUG
    elif quiet:
        ui_logging = logging.FATAL
    else:
        ui_logging = logging.INFO
    # This logger is responsible for user output
    UIHandler = logging.StreamHandler(sys.stderr)
    # the "handler" log level takes priority over so you might think that just
    # setting "DEBUG" here would be enough to implement "--verbose".
    # That is not enough, so we need to set the level also on the logger (see below).
    UIHandler.setLevel(ui_logging)
    UIHandler.setFormatter(logging.Formatter('%(message)s'))
    mq_logger = logging.getLogger('mailqueue')
    # If not we don't set a level for the "mailqueue" logger all other loggers
    # will inherit the root logger's log level (which is WARNING by default).
    # That will suppress a lot of log messages.
    mq_logger.setLevel(ui_logging)
    mq_logger.addHandler(UIHandler)
    # messages from the "mailqueue" handler should typically not bubble up to
    # the root logger (this might lead to duplicate lines shown to the user,
    # e.g. in case of errors).
    mq_logger.propagate = False

