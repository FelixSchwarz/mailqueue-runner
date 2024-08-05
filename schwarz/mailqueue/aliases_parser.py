"""Parse /etc/aliases"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, TextIO, Tuple, Union


__all__ = ['lookup_address', 'lookup_adresses']

StrPath = Union[str, os.PathLike]

def lookup_address(
        address: str,
        _aliases: Optional[Dict[str, List[str]]] = None,
    ) -> Optional[Tuple[str]]:
    if _is_email_address(address):
        return (address,)
    aliases = _load_aliases(_aliases)
    if not aliases:
        return None
    return _resolve_alias(address, aliases)


def lookup_adresses(recipients: Sequence[str], aliases: Optional[dict]) -> Tuple[str]:
    email_addresses = []
    for recipient in recipients:
        targets = lookup_address(recipient, aliases)
        email_addresses = _extend(email_addresses, targets)
    return tuple(email_addresses)


def _resolve_alias(address: str, aliases) -> Optional[Tuple[str]]:
    if _is_email_address(address):
        return (address,)

    targets = aliases.get(address)
    if not targets:
        return None
    email_addresses = []
    for target in targets:
        if _is_email_address(target):
            email_addresses = _extend(email_addresses, [target])
        else:
            _extra_adresses = _resolve_alias(target, aliases)
            email_addresses = _extend(email_addresses, _extra_adresses)
    return tuple(email_addresses)


def _is_email_address(address: Optional[str]) -> bool:
    return address and ('@' in address)


def _extend(values, new_values):
    _new = list(values)
    if new_values:
        for value in new_values:
            if value not in _new:
                _new.append(value)
    return _new


def _load_aliases(aliases):
    if not aliases:
        system_aliases = Path('/etc/aliases')
        if system_aliases.exists():
            return _parse_aliases(system_aliases)
    return aliases


def _parse_aliases(src: Union[StrPath, TextIO]) -> Dict[str, List[str]]:
    if isinstance(src, (os.PathLike, str)):
        with open(src) as aliases_fp:
            aliases_str = aliases_fp.read()
    else:
        aliases_str = src.read()

    _aliases = {}
    re_colon = re.compile(r'\s*:\s*')
    re_items = re.compile(r'\s*,\s*')
    for line_str in re.split(r'\n+', aliases_str):
        alias_line = line_str.split('#', 1)[0].strip()
        if not alias_line:
            continue
        if ':' not in alias_line:
            # faulty alias line
            continue
        _alias, _target = re_colon.split(alias_line, 1)
        _aliases[_alias] = list(re_items.split(_target))

    return _aliases
