#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals, absolute_import

from arrow.arrow import Arrow
from datetime import timedelta

from uuid import uuid4
from dateutil.tz import gettz
import arrow
import re
from typing import Dict, Optional, List, Union, Tuple
from .parse import Container, ContentLine

from . import parse

tzutc = arrow.utcnow().tzinfo


def remove_x(container: Container) -> None:
    for i in reversed(range(len(container))):
        item = container[i]
        if item.name.startswith('X-'):
            del container[i]


def remove_sequence(container: Container) -> None:
    for i in reversed(range(len(container))):
        item = container[i]
        if item.name == 'SEQUENCE':
            del container[i]


DATE_FORMATS: Dict[int, str] = dict((len(k), k) for k in (
    'YYYYMM',
    'YYYYMMDD',
    'YYYYMMDDTHH',
    'YYYYMMDDTHHmm',
    'YYYYMMDDTHHmmss'))


def arrow_get(string: str) -> Arrow:
    '''this function exists because ICS uses ISO 8601 without dashes or
    colons, i.e. not ISO 8601 at all.'''

    # replace slashes with dashes
    if '/' in string:
        string = string.replace('/', '-')

    # if string contains dashes, assume it to be proper ISO 8601
    if '-' in string:
        return arrow.get(string)

    string = string.rstrip('Z')
    return arrow.get(string, DATE_FORMATS[len(string)])


def iso_to_arrow(time_container: Optional[ContentLine], available_tz={}) -> Arrow:
    if time_container is None:
        return None

    # TODO : raise if not iso date
    tz_list = time_container.params.get('TZID')
    # TODO : raise if len(tz_list) > 1 or if tz is not a valid tz
    # TODO : see if timezone is registered as a VTIMEZONE
    if tz_list and len(tz_list) > 0:
        tz = tz_list[0]
    else:
        tz = None
    if ('T' not in time_container.value) and \
            'DATE' in time_container.params.get('VALUE', []):
        val = time_container.value + 'T0000'
    else:
        val = time_container.value

    if tz and not (val[-1].upper() == 'Z'):
        naive = arrow_get(val).naive
        selected_tz = gettz(tz)
        if not selected_tz:
            selected_tz = available_tz.get(tz, 'UTC')
        return arrow.get(naive, selected_tz)
    else:
        return arrow_get(val)

    # TODO : support floating (ie not bound to any time zone) times (cf
    # http://www.kanzaki.com/docs/ical/dateTime.html)


def iso_precision(string: str) -> str:
    has_time = 'T' in string

    if has_time:
        date_string, time_string = string.split('T', 1)
        time_parts = re.split('[+-]', time_string, 1)
        has_seconds = time_parts[0].count(':') > 1
        has_seconds = not has_seconds and len(time_parts[0]) == 6

        if has_seconds:
            return 'second'
        else:
            return 'minute'
    else:
        return 'day'


def get_lines(container: Container, name: str) -> List[ContentLine]:
    lines = []
    for i in reversed(range(len(container))):
        item = container[i]
        if item.name == name:
            lines.append(item)
            del container[i]
    return lines


def parse_duration(line: str) -> timedelta:
    """
    Return a timedelta object from a string in the DURATION property format
    """
    DAYS, SECS = {'D': 1, 'W': 7}, {'S': 1, 'M': 60, 'H': 3600}
    sign, i = 1, 0
    if line[i] in '-+':
        if line[i] == '-':
            sign = -1
        i += 1
    if line[i] != 'P':
        raise parse.ParseError()
    i += 1
    days, secs = 0, 0
    while i < len(line):
        if line[i] == 'T':
            i += 1
            if i == len(line):
                break
        j = i
        while line[j].isdigit():
            j += 1
        if i == j:
            raise parse.ParseError()
        val = int(line[i:j])
        if line[j] in DAYS:
            days += val * DAYS[line[j]]
            DAYS.pop(line[j])
        elif line[j] in SECS:
            secs += val * SECS[line[j]]
            SECS.pop(line[j])
        else:
            raise parse.ParseError()
        i = j + 1
    return timedelta(sign * days, sign * secs)


def timedelta_to_duration(dt: timedelta) -> str:
    """
    Return a string according to the DURATION property format
    from a timedelta object
    """
    days, secs = dt.days, dt.seconds
    res = 'P'
    if days // 7:
        res += str(days // 7) + 'W'
        days %= 7
    if days:
        res += str(days) + 'D'
    if secs:
        res += 'T'
        if secs // 3600:
            res += str(secs // 3600) + 'H'
            secs %= 3600
        if secs // 60:
            res += str(secs // 60) + 'M'
            secs %= 60
        if secs:
            res += str(secs) + 'S'
    return res


def get_arrow(value: Union[None, Arrow, Tuple, Dict]) -> Arrow:
    if value is None:
        return None
    elif isinstance(value, Arrow):
        return value
    elif isinstance(value, tuple):
        return arrow.get(*value)
    elif isinstance(value, dict):
        return arrow.get(**value)
    else:
        return arrow.get(value)


def arrow_to_iso(instant: Arrow) -> str:
    # set to utc, make iso, remove timezone
    instant = arrow.get(instant.astimezone(tzutc)).format('YYYYMMDDTHHmmss')
    return instant + 'Z'


def arrow_date_to_iso(instant: Arrow) -> str:
    # date-only for all day events
    # set to utc, make iso, remove timezone
    instant = arrow.get(instant.astimezone(tzutc)).format('YYYYMMDD')
    return instant  # no TZ for all days


def uid_gen() -> str:
    uid = str(uuid4())
    return "{}@{}.org".format(uid, uid[:4])


def escape_string(string: str) -> str:
    string = string.replace("\\", "\\\\")
    string = string.replace(";", "\\;")
    string = string.replace(",", "\\,")
    string = string.replace("\n", "\\n")
    string = string.replace("\r", "\\r")
    return string


def unescape_string(string: str) -> str:
    string = string.replace("\\;", ";")
    string = string.replace("\\,", ",")
    string = string.replace("\\n", "\n")
    string = string.replace("\\N", "\n")
    string = string.replace("\\r", "\r")
    string = string.replace("\\R", "\r")
    string = string.replace("\\\\", "\\")

    return string
