#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .parse import ContentLine
from typing import Dict, Any


class Attendee(object):

    def __init__(self, email: str, common_name: str = None, rsvp: bool = None) -> None:
        self.email = email
        self.common_name = common_name or email
        self.rsvp = rsvp

    def __str__(self) -> str:
        """Returns the attendee in an iCalendar format."""
        return str(ContentLine('ATTENDEE', params=self._get_params(), value='mailto:%s' % self.email))

    def _get_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if self.common_name:
            params['CN'] = ["'%s'" % self.common_name]

        if self.rsvp:
            params['RSVP'] = [self.rsvp]

        return params
