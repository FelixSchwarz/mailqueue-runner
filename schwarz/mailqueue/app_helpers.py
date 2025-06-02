# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import configparser
import logging
import logging.config
import os
import sys
from pathlib import Path
from typing import Optional

from .mailer import SMTPMailer
from .plugins import PluginLoader, parse_list_str, registry


__all__ = [
    'guess_config_path',
    'init_app',
    'init_smtp_mailer',
]

def init_app(config_path, options=None, settings=None):
    assert (config_path is not None) ^ (settings is not None)
    if settings is None:
        settings = parse_config(config_path, section_name='mqrunner')
    configure_logging(settings, options or {})

    log = logging.getLogger('mailqueue')
    if registry is not None:
        enabled_plugins = parse_list_str(settings.get('plugins', '*'))
        plugin_loader = PluginLoader('mailqueue.plugins', enabled_plugins=enabled_plugins, log=log)
        plugin_loader.initialize_plugins(registry)
    else:
        log.debug('plugin initialization skipped because PuzzlePluginSystem is not available')
        plugin_loader = None
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


def guess_config_path(cfg_path: str) -> Optional[Path]:
    if cfg_path:
        return Path(cfg_path)

    candidates = [os.path.expanduser('~/.mailqueue-runner.conf')]
    if sys.platform == 'linux':
        candidates.append('/etc/mailqueue-runner.conf')
    for candidate in candidates:
        if os.path.exists(candidate):
            return Path(candidate)
    return None


def parse_config(config_path, section_name=None):
    if not config_path:
        sys.stderr.write('No config file found.\n')
        sys.exit(20)
    filename = os.path.basename(config_path)
    if not os.path.exists(config_path):
        sys.stderr.write('config file "%s" not found.\n' % filename)
        sys.exit(20)

    parser = configparser.ConfigParser()
    exc_msg = None
    try:
        # `ConfigParser.read()` silently ignores errors (e.g. "permission denied").
        # Opening the config file first means we get an IOError with a more
        # helpful error message.
        with config_path.open('r') as config_fp:
            parser.read_file(config_fp)
        # ConfigParser in Python 2 has no ".items()" (without parameters)
        sections = (section_name, ) if section_name else parser.sections()
        for section in sections:
            parser.items(section)
    except IOError as io_exc:
        exc_msg = f'Unable to open config file "{config_path}" ({io_exc})'
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
    path_logging_config = settings.get('logging_config')
    basic_logging_configured = settings.get('basic_logging_configured', False)
    delivery_log_file = None
    queue_log_file = None

    if path_logging_config:
        if not os.path.exists(path_logging_config):
            sys.stderr.write('No log configuration file "%s".\n' % path_logging_config)
            sys.exit(25)
        try:
            logging.config.fileConfig(path_logging_config)
        except Exception as e:
            sys.stderr.write('Malformed logging configuration file "%s": %s\n' % (path_logging_config, e))  # noqa: E501 (line-too-long)
            sys.exit(26)
    elif basic_logging_configured:
        pass
    else:
        logging.basicConfig()
        if 'delivery_log' in settings:
            delivery_log_file = settings['delivery_log']
        if 'queue_log' in settings:
            queue_log_file = settings['queue_log']

    if delivery_log_file:
        _setup_file_logger(Path(delivery_log_file), logger_key='mailqueue.delivery_log')
    if queue_log_file:
        _setup_file_logger(Path(queue_log_file), logger_key='mailqueue.queue_log')

    verbose = options.get('verbose')
    quiet = options.get('quiet')
    ui_log_level = _ui_log_level(verbose, quiet)
    add_ui_logger(ui_log_level)


def _setup_file_logger(path_log_file, logger_key):
    log_dir = path_log_file.parent
    log_display_name = 'delivery log' if ('delivery' in logger_key) else 'queue log'
    if not log_dir.exists():
        try:
            log_dir.mkdir(parents=True)
        except OSError as e:
            err_msg = f'Cannot create log directory "{log_dir}" for {log_display_name} log: {e}'
            sys.stderr.write(err_msg + '\n')
            sys.exit(27)

    _h_logfile = logging.FileHandler(path_log_file)
    _h_logfile.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    _logger = logging.getLogger(logger_key)
    _logger.addHandler(_h_logfile)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def _ui_log_level(verbose, quiet):
    if verbose and quiet:
        raise ValueError('Cannot use both "--verbose" and "--quiet".')
    if verbose:
        return logging.DEBUG
    elif quiet:
        return logging.FATAL
    else:
        return logging.INFO


def add_ui_logger(ui_log_level):
    # This logger is responsible for user output
    UIHandler = logging.StreamHandler(sys.stderr)
    # the "handler" log level takes priority over so you might think that just
    # setting "DEBUG" here would be enough to implement "--verbose".
    # That is not enough, so we need to set the level also on the logger (see below).
    UIHandler.setLevel(ui_log_level)
    UIHandler.setFormatter(logging.Formatter('%(message)s'))
    mq_logger = logging.getLogger('mailqueue')
    # If not we don't set a level for the "mailqueue" logger all other loggers
    # will inherit the root logger's log level (which is WARNING by default).
    # That will suppress a lot of log messages.
    mq_logger.setLevel(ui_log_level)
    mq_logger.addHandler(UIHandler)
    # messages from the "mailqueue" handler should typically not bubble up to
    # the root logger (this might lead to duplicate lines shown to the user,
    # e.g. in case of errors).
    mq_logger.propagate = False
