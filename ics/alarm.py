#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals, absolute_import
from typing import Iterable, Union, Set, Dict, List, Callable, Optional, Type

import copy
from datetime import timedelta, datetime

from .component import Component, Extractor
from .utils import (
    arrow_to_iso,
    escape_string,
    get_arrow,
    get_lines,
    iso_to_arrow,
    parse_duration,
    timedelta_to_duration,
    unescape_string
)
from .parse import ContentLine, Container


class Alarm(Component):
    """
    A calendar event VALARM base class
    """

    _TYPE = 'VALARM'
    _EXTRACTORS: List[Extractor] = []
    _OUTPUTS: List[Callable] = []

    def __init__(self,
                 trigger: Union[timedelta, datetime] = None,
                 repeat: int = None,
                 duration: timedelta = None) -> None:
        """
        Instantiates a new :class:`ics.alarm.Alarm`.

        Adheres to RFC5545 VALARM standard: http://icalendar.org/iCalendar-RFC-5545/3-6-6-alarm-component.html

        Args:
            trigger (datetime.timedelta OR datetime.datetime) : Timespan to alert before parent action, or absolute time to alert
            repeat (integer) : How many times to repeat the alarm
            duration (datetime.timedelta) : Duration between repeats

        Raises:
            ValueError: If trigger, repeat, or duration do not match the RFC spec.
        """
        # Set initial values
        self._trigger: Optional[Union[timedelta, datetime]] = None
        self._repeat: Optional[int] = None
        self._duration: Optional[timedelta] = None

        # Validate and parse
        self.trigger = trigger

        # XOR repeat and duration
        if (repeat is None) ^ (duration is None):
            raise ValueError('If either repeat or duration is specified, both must be specified')

        if repeat:
            self.repeat = repeat

        if duration:
            self.duration = duration

        self._unused = Container(name='VALARM')

    @property
    def trigger(self) -> Optional[Union[timedelta, datetime]]:
        """The trigger condition for the alarm

        | Returns either a timedelta or datetime object
        | Timedelta must have positive total_seconds()
        | Datetime object is also allowed.
        """
        return self._trigger

    @trigger.setter
    def trigger(self, value: Optional[Union[timedelta, datetime]]) -> None:
        if isinstance(value, timedelta) and value.total_seconds() < 0:
            raise ValueError('Trigger timespan must be positive')
        elif isinstance(value, datetime):
            value = get_arrow(value)

        self._trigger = value

    @property
    def repeat(self) -> Optional[int]:
        """Number of times to repeat alarm

        | Returns an integer for number of alarm repeats
        | Value must be >= 0
        """
        return self._repeat

    @repeat.setter
    def repeat(self, value: Optional[int]) -> None:
        if value is not None and value < 0:
            raise ValueError('Repeat must be great than or equal to 0.')

        self._repeat = value

    @property
    def duration(self) -> Optional[timedelta]:
        """Duration between alarm repeats

        | Returns a timedelta object
        | Timespan must return positive total_seconds() value
        """
        return self._duration

    @duration.setter
    def duration(self, value: Optional[timedelta]) -> None:
        if value is not None and value.total_seconds() < 0:
            raise ValueError('Alarm duration timespan must be positive.')

        self._duration = value

    @property
    def action(self):
        """ VALARM action to be implemented by concrete classes
        """
        raise NotImplementedError('Base class cannot be instantiated directly')

    def __repr__(self) -> str:
        value = '{0} trigger:{1}'.format(type(self), self.trigger)
        if self.repeat:
            value += ' repeat:{0} duration:{1}'.format(self.repeat, self.duration)

        return '<{0}>'.format(value)

    def __hash__(self) -> int:
        return hash(repr(self))

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __eq__(self, other) -> bool:
        """Two alarms are considered equal if they have the same type and base values."""

        return (type(self) is type(other) and
                self.trigger == other.trigger and
                self.repeat == other.repeat and
                self.duration == other.duration)

    def clone(self):
        """
        Returns:
            Alarm: an exact copy of self"""
        clone = copy.copy(self)
        clone._unused = clone._unused.clone()
        return clone


class AlarmFactory(object):
    """
    Factory class to get specific VALARM types, useful with `ics.component.Component._from_container` method.
    """

    @classmethod
    def get_type_from_action(cls, action_type: str) -> Type[Alarm]:
        # TODO: Implement EMAIL action
        if action_type == 'DISPLAY':
            return DisplayAlarm
        elif action_type == 'AUDIO':
            return AudioAlarm
        # FIXME mypy
        # elif action_type == 'NONE':
        #     return None

        raise ValueError('Invalid alarm action')

    @classmethod
    def get_type_from_container(cls, container: Container) -> Type[Alarm]:
        action_type_lines = get_lines(container, 'ACTION')
        if len(action_type_lines) > 1:
            raise ValueError('Too many ACTION parameters in VALARM')

        action_type = action_type_lines[0]
        return AlarmFactory.get_type_from_action(action_type.value)


# ------------------
# ----- Inputs -----
# ------------------
@Alarm._extracts('TRIGGER', required=True)
def trigger(alarm: Alarm, line: ContentLine):
    if not line.params or 'DURATION' in line.params.get('VALUE', ''):
        alarm.trigger = parse_duration(line.value[1:])
    else:
        if len(line.params) > 1:
            raise ValueError('TRIGGER has too many parameters')

        if 'VALUE' in line.params:
            alarm.trigger = iso_to_arrow(line)
        else:
            raise ValueError('TRIGGER has invalid parameters')


@Alarm._extracts('DURATION')
def duration(alarm: Alarm, line: ContentLine):
    if line:
        alarm._duration = parse_duration(line.value)


@Alarm._extracts('REPEAT')
def repeat(alarm: Alarm, line: ContentLine):
    if line:
        alarm._repeat = int(line.value)


# -------------------
# ----- Outputs -----
# -------------------
@Alarm._outputs
def o_trigger(alarm, container):
    if not alarm.trigger:
        raise ValueError('Alarm must have a trigger')

    if type(alarm.trigger) is timedelta:
        representation = timedelta_to_duration(alarm.trigger)
        container.append(ContentLine('TRIGGER', value='-{0}'.format(representation)))
    else:
        container.append(ContentLine('TRIGGER',
                                     params={'VALUE': ['DATE-TIME']},
                                     value=arrow_to_iso(alarm.trigger)))


@Alarm._outputs
def o_duration(alarm, container):
    if alarm.duration:
        representation = timedelta_to_duration(alarm.duration)
        container.append(ContentLine('DURATION', value=representation))


@Alarm._outputs
def o_repeat(alarm, container):
    if alarm.repeat:
        container.append(ContentLine('REPEAT', value=alarm.repeat))


@Alarm._outputs
def o_action(alarm, container):
    container.append(ContentLine('ACTION', value=alarm.action))


class DisplayAlarm(Alarm):
    """
    A calendar event VALARM with DISPLAY option.
    """

    # This ensures we copy the existing extractors and outputs from the base class, rather than referencing the array.
    _EXTRACTORS = copy.copy(Alarm._EXTRACTORS)
    _OUTPUTS = copy.copy(Alarm._OUTPUTS)

    def __init__(self,
                 description=None,
                 **kwargs):
        """
        Instantiates a new :class:`ics.alarm.DisplayAlarm`.

        Adheres to RFC5545 VALARM standard: http://icalendar.org/iCalendar-RFC-5545/3-6-6-alarm-component.html

        Args:
            description (string) : RFC5545 DESCRIPTION property
            kwargs (dict) : Args to :func:`ics.alarm.Alarm.__init__`
        """
        super(DisplayAlarm, self).__init__(**kwargs)
        self.description = description

    @property
    def action(self):
        return 'DISPLAY'

    def __repr__(self):
        value = '{0} trigger:{1}'.format(type(self), self.trigger)
        if self.repeat:
            value += ' repeat:{0} duration:{1}'.format(self.repeat, self.duration)

        value += ' description:{0}'.format(self.description)

        return '<{0}>'.format(value)


# ------------------
# ----- Inputs -----
# ------------------
@DisplayAlarm._extracts('DESCRIPTION', required=True)
def description(alarm: DisplayAlarm, line: ContentLine):
    alarm.description = unescape_string(line.value) if line else None


# -------------------
# ----- Outputs -----
# -------------------
@DisplayAlarm._outputs
def o_description(alarm, container):
    container.append(ContentLine('DESCRIPTION', value=escape_string(alarm.description or '')))


class AudioAlarm(Alarm):
    """
    A calendar event VALARM with AUDIO option.
    """

    # This ensures we copy the existing extractors and outputs from the base class, rather than referencing the array.
    _EXTRACTORS = copy.copy(Alarm._EXTRACTORS)
    _OUTPUTS = copy.copy(Alarm._OUTPUTS)

    def __init__(self,
                 attach=None,
                 attach_params=None,
                 **kwargs):
        """
        Instantiates a new :class:`ics.alarm.AudioAlarm`.

        Adheres to RFC5545 VALARM standard: http://icalendar.org/iCalendar-RFC-5545/3-6-6-alarm-component.html

        Args:
            attach (string) : RFC5545 ATTACH property, pointing to an audio object
            attach_params (dict) : RFC5545 attachparam values
            kwargs (dict) : Args to :func:`ics.alarm.Alarm.__init__`
        """
        super(AudioAlarm, self).__init__(**kwargs)
        self.attach = attach
        self.attach_params = attach_params

    @property
    def action(self):
        return 'AUDIO'

    def __repr__(self):
        value = '{0} trigger:{1}'.format(type(self), self.trigger)
        if self.repeat:
            value += ' repeat:{0} duration:{1}'.format(self.repeat, self.duration)

        if self.attach:
            value += ' attach:{0}'.format(self.attach)
            if self.attach_params:
                value += ' attach_params:{0}'.format(self.attach_params)

        return '<{0}>'.format(value)


# ------------------
# ----- Inputs -----
# ------------------
@AudioAlarm._extracts('ATTACH')
def attach(alarm: AudioAlarm, line: ContentLine):
    if line:
        if line.value:
            alarm.attach = unescape_string(line.value)

        if line.params:
            alarm.attach_params = line.params


# -------------------
# ----- Outputs -----
# -------------------
@AudioAlarm._outputs
def o_attach(alarm, container):
    if alarm.attach:
        container.append(ContentLine('ATTACH', params=alarm.attach_params or {}, value=escape_string(alarm.attach)))
