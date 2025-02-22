#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals, absolute_import
from typing import Iterable, Union, Set, Dict, List, Callable, Optional


from six.moves import map

import arrow
import copy
from datetime import timedelta, datetime

from .alarm import AlarmFactory, Alarm
from .component import Component, Extractor
from .utils import (
    parse_duration,
    timedelta_to_duration,
    iso_to_arrow,
    get_arrow,
    arrow_to_iso,
    uid_gen,
    unescape_string,
    escape_string,
)
from .parse import ContentLine, Container


class Todo(Component):

    """A todo list entry.

    Can have a start time and duration, or start and due time,
    or only start/due time.
    """

    _TYPE = "VTODO"
    _EXTRACTORS: List[Extractor] = []
    _OUTPUTS: List[Callable] = []

    def __init__(self,
                 dtstamp=None,
                 uid: str = None,
                 completed=None,
                 created=None,
                 description: str = None,
                 begin=None,
                 location: str = None,
                 percent: int = None,
                 priority: int = None,
                 name: str = None,
                 url: str = None,
                 due=None,
                 duration: timedelta = None,
                 alarms: Iterable[Alarm] = None,
                 status: str = None):
        """Instantiates a new :class:`ics.todo.Todo`.

        Args:
            uid (string): must be unique
            dtstamp (Arrow-compatible)
            completed (Arrow-compatible)
            created (Arrow-compatible)
            description (string)
            begin (Arrow-compatible)
            location (string)
            percent (int): 0-100
            priority (int): 0-9
            name (string) : rfc5545 SUMMARY property
            url (string)
            due (Arrow-compatible)
            duration (datetime.timedelta)
            alarms (:class:`ics.alarm.Alarm`)
            status (string)

        Raises:
            ValueError: if `duration` and `due` are specified at the same time
        """

        self._percent: Optional[int] = None
        self._priority: Optional[int] = None
        self._begin = None
        self._due_time = None
        self._duration = None

        self.uid = uid_gen() if not uid else uid
        self.dtstamp = arrow.now() if not dtstamp else get_arrow(dtstamp)
        self.completed = get_arrow(completed)
        self.created = get_arrow(created)
        self.description = description
        self.begin = begin
        self.location = location
        self.percent = percent
        self.priority = priority
        self.name = name
        self.url = url
        self.alarms: List[Alarm] = list()
        self._unused = Container(name='VTODO')

        if duration and due:
            raise ValueError(
                'Todo() may not specify a duration and due date\
                at the same time')
        elif duration:
            if not begin:
                raise ValueError(
                    'Todo() must specify a begin if a duration\
                    is specified')
            self.duration = duration
        elif due:
            self.due = due

        if alarms is not None:
            self.alarms = list(alarms)
        self.status = status

    @property
    def percent(self) -> Optional[int]:
        return self._percent

    @percent.setter
    def percent(self, value: Optional[int]):
        if value:
            value = int(value)
            if value < 0 or value > 100:
                raise ValueError('percent must be [0, 100]')
        self._percent = value

    @property
    def priority(self) -> Optional[int]:
        return self._priority

    @priority.setter
    def priority(self, value: Optional[int]):
        if value:
            value = int(value)
            if value < 0 or value > 9:
                raise ValueError('priority must be [0, 9]')
        self._priority = value

    @property
    def begin(self):
        """Get or set the beginning of the todo.

        |  Will return an :class:`Arrow` object.
        |  May be set to anything that :func:`Arrow.get` understands.
        |  If a due time is defined (not a duration), .begin must not
            be set to a superior value.
        """
        return self._begin

    @begin.setter
    def begin(self, value):
        value = get_arrow(value)
        if value and self._due_time and value > self._due_time:
            raise ValueError('Begin must be before due time')
        self._begin = value

    @property
    def due(self):
        """Get or set the end of the todo.

        |  Will return an :class:`Arrow` object.
        |  May be set to anything that :func:`Arrow.get` understands.
        |  If set to a non null value, removes any already
            existing duration.
        |  Setting to None will have unexpected behavior if
            begin is not None.
        |  Must not be set to an inferior value than self.begin.
        """

        if self._duration:
            # if due is duration defined return the beginning + duration
            return self.begin + self._duration
        elif self._due_time:
            # if due is time defined
            return self._due_time
        else:
            return None

    @due.setter
    def due(self, value):
        value = get_arrow(value)
        if value and self._begin and value < self._begin:
            raise ValueError('Due must be after begin')

        self._due_time = value

        if value:
            self._duration = None

    @property
    def duration(self):
        """Get or set the duration of the todo.

        |  Will return a timedelta object.
        |  May be set to anything that timedelta() understands.
        |  May be set with a dict ({"days":2, "hours":6}).
        |  If set to a non null value, removes any already
            existing end time.
        """
        if self._duration:
            return self._duration
        elif self.due:
            return self.due - self.begin
        else:
            # todo has neither due, nor start and duration
            return None

    @duration.setter
    def duration(self, value):
        if isinstance(value, dict):
            value = timedelta(**value)
        elif isinstance(value, timedelta):
            value = value
        elif value is not None:
            value = timedelta(value)

        self._duration = value

        if value:
            self._due_time = None

    @property
    def status(self) -> Optional[str]:
        return self._status

    @status.setter
    def status(self, value: Optional[str]):
        if isinstance(value, str):
            value = value.upper()
        statuses = (None, 'NEEDS-ACTION', 'COMPLETED', 'IN-PROCESS', 'CANCELLED')
        if value not in statuses:
            raise ValueError('status must be one of %s' % ", ".join([repr(x) for x in statuses]))
        self._status = value

    def __repr__(self) -> str:
        if self.name is None:
            return "<Todo>"
        if self.begin is None and self.due is None:
            return "<Todo '{}'>".format(self.name)
        if self.due is None:
            return "<Todo '{}' begin:{}>".format(self.name, self.begin)
        if self.begin is None:
            return "<Todo '{}' due:{}>".format(self.name, self.due)
        return "<Todo '{}' begin:{} due:{}>".format(self.name, self.begin, self.due)

    def __lt__(self, other) -> bool:
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                if self.name is None and other.name is None:
                    return False
                elif self.name is None:
                    return True
                elif other.name is None:
                    return False
                else:
                    return self.name < other.name
            return self.due < other.due
        if isinstance(other, datetime):
            if self.due:
                return self.due < other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __le__(self, other) -> bool:
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                if self.name is None and other.name is None:
                    return True
                elif self.name is None:
                    return True
                elif other.name is None:
                    return False
                else:
                    return self.name <= other.name
            return self.due <= other.due
        if isinstance(other, datetime):
            if self.due:
                return self.due <= other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __gt__(self, other) -> bool:
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                if self.name is None and other.name is None:
                    return False
                elif self.name is None:
                    return False
                elif other.name is None:
                    return True
                else:
                    return self.name > other.name
            return self.due > other.due
        if isinstance(other, datetime):
            if self.due:
                return self.due > other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __ge__(self, other) -> bool:
        if isinstance(other, Todo):
            if self.due is None and other.due is None:
                if self.name is None and other.name is None:
                    return True
                elif self.name is None:
                    return True
                elif other.name is None:
                    return False
                else:
                    return self.name >= other.name
            return self.due >= other.due
        if isinstance(other, datetime):
            if self.due:
                return self.due >= other
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __eq__(self, other) -> bool:
        """Two todos are considered equal if they have the same uid."""
        if isinstance(other, Todo):
            return self.uid == other.uid
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def __ne__(self, other) -> bool:
        """Two todos are considered not equal if they do not have the same uid."""
        if isinstance(other, Todo):
            return self.uid != other.uid
        raise NotImplementedError(
            'Cannot compare Todo and {}'.format(type(other)))

    def clone(self):
        """
        Returns:
            Todo: an exact copy of self"""
        clone = copy.copy(self)
        clone._unused = clone._unused.clone()
        clone.alarms = copy.copy(self.alarms)
        return clone

    def __hash__(self):
        """
        Returns:
            int: hash of self. Based on self.uid."""
        return int(''.join(map(lambda x: '%.3d' % ord(x), self.uid)))


# ------------------
# ----- Inputs -----
# ------------------
@Todo._extracts('DTSTAMP', required=True)
def dtstamp(todo: Todo, line: ContentLine):
    if line:
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo.dtstamp = iso_to_arrow(line, tz_dict)


# TODO : add option somewhere to ignore some errors
@Todo._extracts('UID', required=True)
def uid(todo: Todo, line: ContentLine):
    if line:
        todo.uid = line.value


@Todo._extracts('COMPLETED')
def completed(todo: Todo, line: ContentLine):
    if line:
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo.completed = iso_to_arrow(line, tz_dict)


@Todo._extracts('CREATED')
def created(todo: Todo, line: ContentLine):
    if line:
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo.created = iso_to_arrow(line, tz_dict)


@Todo._extracts('DESCRIPTION')
def description(todo: Todo, line: ContentLine):
    todo.description = unescape_string(line.value) if line else None


@Todo._extracts('DTSTART')
def start(todo: Todo, line: ContentLine):
    if line:
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo.begin = iso_to_arrow(line, tz_dict)


@Todo._extracts('LOCATION')
def location(todo: Todo, line: ContentLine):
    todo.location = unescape_string(line.value) if line else None


@Todo._extracts('PERCENT-COMPLETE')
def percent(todo: Todo, line: ContentLine):
    todo.percent = line.value if line else None


@Todo._extracts('PRIORITY')
def priority(todo: Todo, line: ContentLine):
    todo.priority = line.value if line else None


@Todo._extracts('SUMMARY')
def summary(todo: Todo, line: ContentLine):
    todo.name = unescape_string(line.value) if line else None


@Todo._extracts('URL')
def url(todo: Todo, line: ContentLine):
    todo.url = unescape_string(line.value) if line else None


@Todo._extracts('DUE')
def due(todo: Todo, line: ContentLine):
    if line:
        #TODO: DRY [1]
        if todo._duration:
            raise ValueError("A todo can't have both DUE and DURATION")
        # get the dict of vtimezones passed to the classmethod
        tz_dict = todo._classmethod_kwargs['tz']
        todo._due_time = iso_to_arrow(line, tz_dict)


@Todo._extracts('DURATION')
def duration(todo: Todo, line: ContentLine):
    if line:
        #TODO: DRY [1]
        if todo._due_time:  # pragma: no cover
            raise ValueError("An todo can't have both DUE and DURATION")
        todo._duration = parse_duration(line.value)


@Todo._extracts('VALARM', multiple=True)
def alarms(todo: Todo, lines: List[ContentLine]):
    def alarm_factory(x):
        af = AlarmFactory.get_type_from_container(x)
        return af._from_container(x)

    todo.alarms = list(map(alarm_factory, lines))


@Todo._extracts('STATUS')
def status(todo: Todo, line: ContentLine):
    if line:
        todo.status = line.value


# -------------------
# ----- Outputs -----
# -------------------
@Todo._outputs
def o_dtstamp(todo: Todo, container: Container):
    if todo.dtstamp:
        instant = todo.dtstamp
    else:
        instant = arrow.now()

    container.append(ContentLine('DTSTAMP',
                                 value=arrow_to_iso(instant)))


@Todo._outputs
def o_uid(todo: Todo, container: Container):
    if todo.uid:
        uid = todo.uid
    else:
        uid = uid_gen()

    container.append(ContentLine('UID', value=uid))


@Todo._outputs
def o_completed(todo: Todo, container: Container):
    if todo.completed:
        container.append(ContentLine('COMPLETED',
                                     value=arrow_to_iso(todo.completed)))


@Todo._outputs
def o_created(todo: Todo, container: Container):
    if todo.created:
        container.append(ContentLine('CREATED',
                                     value=arrow_to_iso(todo.created)))


@Todo._outputs
def o_description(todo: Todo, container: Container):
    if todo.description:
        container.append(ContentLine('DESCRIPTION',
                                     value=escape_string(todo.description)))


@Todo._outputs
def o_start(todo: Todo, container: Container):
    if todo.begin:
        container.append(ContentLine('DTSTART',
                                     value=arrow_to_iso(todo.begin)))


@Todo._outputs
def o_location(todo: Todo, container: Container):
    if todo.location:
        container.append(ContentLine('LOCATION',
                                     value=escape_string(todo.location)))


@Todo._outputs
def o_percent(todo: Todo, container: Container):
    if todo.percent is not None:
        container.append(ContentLine('PERCENT-COMPLETE',
                                     value=str(todo.percent)))


@Todo._outputs
def o_priority(todo: Todo, container: Container):
    if todo.priority is not None:
        container.append(ContentLine('PRIORITY',
                                     value=str(todo.priority)))


@Todo._outputs
def o_summary(todo: Todo, container: Container):
    if todo.name:
        container.append(ContentLine('SUMMARY',
                                     value=escape_string(todo.name)))


@Todo._outputs
def o_url(todo: Todo, container: Container):
    if todo.url:
        container.append(ContentLine('URL',
                                     value=escape_string(todo.url)))


@Todo._outputs
def o_due(todo: Todo, container: Container):
    if todo._due_time:
        container.append(ContentLine('DUE',
                                     value=arrow_to_iso(todo._due_time)))


@Todo._outputs
def o_duration(todo: Todo, container: Container):
    if todo._duration:
        representation = timedelta_to_duration(todo._duration)
        container.append(ContentLine('DURATION',
                                     value=representation))


@Todo._outputs
def o_alarm(todo: Todo, container: Container):
    for alarm in todo.alarms:
        container.append(str(alarm))


@Todo._outputs
def o_status(todo: Todo, container: Container):
    if todo.status:
        container.append(ContentLine('STATUS', value=todo.status))
