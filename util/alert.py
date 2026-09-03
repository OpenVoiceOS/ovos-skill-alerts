# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import datetime as dt
import json
from time import time
from typing import Set, Optional, Union, List
from uuid import uuid4
from zoneinfo import ZoneInfo

import icalendar
from dateutil.relativedelta import relativedelta
from json_database.utils import merge_dict
from ovos_config import Configuration
from ovos_config.locale import get_default_tz, get_default_lang
from ovos_skill_alerts.util import AlertType, DAVType, AlertPriority, Weekdays
from ovos_skill_alerts.util.dav_utils import process_ical_event, process_ical_todo
from ovos_utils.log import LOG

LOCAL_USER = "local"
TZID = Configuration().get("location", {}).get("timezone", {}).get("code") or "UTC"


def alert_time_in_range(
        start: dt.datetime,
        end: Optional[dt.datetime],
        ref_start: dt.datetime,
        ref_end: Optional[dt.datetime]
) -> bool:
    """
    Checks if two alerts with given start and end datetimes
    overlap each other. 
    :param start: datetime
    :param end: datetime, mostly end dt of timespan check
    :param ref_start: event reference start datetime
    :param ref_end: event reference end datetime
    :returns: bool
    """
    # no duration on both
    if ref_end is None and end is None:
        return False
    if end is not None:
        return (start <= ref_start < end) \
            or (start <= ref_end < end if ref_end else False)
    # in this case it's the reverse question
    return ref_start <= start < ref_end


class Alert:
    def __init__(self, data: dict = None):
        if not isinstance(data, dict):
            raise ValueError(f"Expected a dict, but got: {type(data)}")
        self._data = data or dict()

    @property
    def data(self) -> dict:
        """
        Return a json-dumpable dict representation of this alert
        """
        return self._data

    @property
    def serialize(self) -> str:
        """
        Return a string representation of the alert
        """
        return json.dumps(self._data)

    @property
    def user(self) -> str:
        """
        Return the user associated with this alert
        """
        return self.context.get("username") \
            or self.context.get("user") \
            or LOCAL_USER

    @property
    def lang(self) -> str:
        """
        Returns the lang associated with this alert
        """
        return self._data.get("lang") or get_default_lang()

    @property
    def created(self) -> dt.datetime:
        """
        Return the datetime the alert was created
        """
        dt_ = dt.datetime.fromtimestamp(self.context.get("created"))
        return dt_.astimezone(self.timezone).replace(microsecond=0)

    @property
    def stopwatch(self):
        """
        Returns the time elapsed since the alert was created
        """
        return self.now - self.created

    @property
    def stopwatch_mode(self):
        """
        Returns the stopwatch mode
        """
        return self.alert_type == AlertType.TIMER and \
            self.context.get("stopwatch_mode", False)

    @stopwatch_mode.setter
    def stopwatch_mode(self, mode: bool):
        """
        Sets the stopwatch mode
        """
        self.add_context({"stopwatch_mode": mode})

    @property
    def timezone(self) -> dt.tzinfo:
        """
        Tzinfo associated with this alert's expiration
        """
        expiration = self._data.get("next_expiration_time")
        return dt.datetime.fromisoformat(expiration).tzinfo if expiration \
            else get_default_tz()

    @property
    def timezone_name(self) -> str:
        """
        IANA name of the zone a wall-clock repeat of this alert is read in.
        Unlike `timezone`, which only carries the fixed offset the expiration
        was written with, this survives a daylight-saving transition.
        """
        return self._data.get("timezone") or \
            Configuration().get("location", {}).get("timezone", {}).get("code") \
            or "UTC"

    @property
    def alert_type(self) -> AlertType:
        """
        :returns: the associated Alert type Enum
        """
        return AlertType(self._data.get("alert_type", 99))

    @alert_type.setter
    def alert_type(self, type_: AlertType):
        if not isinstance(type_, AlertType):
            raise TypeError("alert_type must be of type AlertType")
        self._data["alert_type"] = type_.value

    @property
    def dav_type(self) -> DAVType:
        """
        :returns: the associated DAV type Enum (VTODO,VEVENT)
        """
        return DAVType(self._data.get("dav_type", 1))

    @dav_type.setter
    def dav_type(self, _type: DAVType):
        if not isinstance(_type, DAVType):
            raise TypeError("dav_type must be of type DAVType")
        self._data["dav_type"] = _type.value

    @property
    def ident(self) -> str:
        """
        :returns: the uuid identifier of the alert
        """
        return self.context.get("ident")

    @property
    def related_to(self) -> str:
        """
        :returns: the parent uuid the alert is associated with
        """
        return self.context.get("related_to", "")

    @property
    def children(self) -> List[str]:
        """
        :returns: list of child uuid the alert is associated with
        """
        return self.context.get("parent_to", [])

    @property
    def priority(self) -> int:
        """
        :returns: the alert priority (1-10)
        """
        return self._data.get("priority") or AlertPriority.AVERAGE.value

    @priority.setter
    def priority(self, num: int):
        """
        store the alert priority (1-10)
        """
        self._data["priority"] = num

    @property
    def context(self) -> dict:
        """
        Returns the contextual info of the alert
        """
        return self._data.get("context") or dict()

    @property
    def message_context(self) -> dict:
        """
        Returns the creating message's bus context (session, source,
        destination, etc.), held verbatim since creation so a re-offer to
        the scheduler does not strip a satellite's routing identity.
        """
        return self._data.get("message_context") or dict()

    @property
    def alert_name(self) -> str:
        """
        Returns the name of the alert
        """
        return self._data.get("alert_name")

    @property
    def now(self):
        return dt.datetime.now(tz=self.timezone)

    # Expiration
    @property
    def prenotification(self) -> Optional[dt.datetime]:
        """
        Returns the datetime to be noticed prior to the actual event
        """
        if self._data.get("prenotification") is None or self.expiration is None:
            return None
        notification = self.expiration + dt.timedelta(
            seconds=self._data.get("prenotification")
        )
        return notification if notification > self.now else None

    @prenotification.setter
    def prenotification(self, time_: Union[dt.timedelta, dt.datetime, relativedelta, int]):
        if self.expiration is None:
            raise Exception("You can't set a prenotification without expiration")
        elif isinstance(time_, (dt.timedelta, relativedelta)):
            if isinstance(time_, relativedelta):
                now = self.now
                time_ = now + time_ - now
            secs_before = int(time_.total_seconds())
            if secs_before > 0:
                secs_before *= -1
        elif isinstance(time_, dt.datetime):
            secs_before = int((time_ - self.expiration).total_seconds())
        elif isinstance(time_, int):
            secs_before = time_
        else:
            raise TypeError("prenotification must be a datetime/timedelta/int object")
        self._data["prenotification"] = secs_before

    @property
    def expiration(self) -> Optional[dt.datetime]:
        """
        Return the next valid expiration time for this alert. Returns None if
        the alert is expired and has no valid repeat options. If there is a
        valid repeat, the alert will no longer report as expired.
        """
        return self._get_next_expiration_time()

    @expiration.setter
    def expiration(self, new_expiration: Union[dt.datetime, dt.date]):
        if new_expiration.__class__ == dt.date:
            new_expiration = dt.datetime.combine(new_expiration, dt.time.min) \
                .replace(tzinfo=self.timezone)
        self._data["next_expiration_time"] = new_expiration.isoformat()

    @property
    def has_expiration(self) -> bool:
        """
        Returns whether the alert has an experiation date of any kind
        (expiration/prenotification).
        """
        return any([self.prenotification, self.expiration])

    @property
    def is_expired(self) -> bool:
        """
        Return True if this alert expired, this does not account for any
        repeat behavior and reports using the last determined expiration time
        """
        expiration = self._data.get("next_expiration_time")
        if expiration is None:
            return False
        now = dt.datetime.now(self.timezone)
        return now >= dt.datetime.fromisoformat(expiration)

    @property
    def is_all_day(self) -> bool:
        """
        Returns whether the alert is a whole day alert
        """
        if self.expiration is None:
            return False
        return self._data.get("all_day", False)

    @is_all_day.setter
    def is_all_day(self, all_day: bool):
        """
        Sets the all_day property
        """
        self._data["all_day"] = all_day
        if all_day:
            self._data["next_expiration_time"] = \
                (self.expiration.replace(hour=0, minute=0, second=0)).isoformat()
            self.until = (self.until or self.expiration).replace(hour=23, minute=59, second=59)

    @property
    def time_to_expiration(self) -> dt.timedelta:
        """
        Return the time until `next_expiration_time` (negative) if alert expired.
        This does not account for any repeat behavior, call `expiration`
        to check for a repeating event.
        """
        if not self._data.get("next_expiration_time", False):
            return dt.timedelta(0)
        now = dt.datetime.now(self.timezone)
        return dt.datetime.fromisoformat(self._data.get("next_expiration_time")) - now

    # Repeat Information
    @property
    def repeat_days(self) -> Optional[Set[Weekdays]]:
        """
        :returns: A set of Weekdays the alert is set up with
        """
        return (
            set([Weekdays(d) for d in self._data.get("repeat_days")])
            if self._data.get("repeat_days")
            else None
        )

    @property
    def repeat_frequency(self) -> Optional[dt.timedelta]:
        """
        :returns: A timedelta object of the repeat frequency
        """
        return (
            dt.timedelta(seconds=self._data.get("repeat_frequency"))
            if self._data.get("repeat_frequency")
            else None
        )

    @property
    def has_repeat(self) -> bool:
        """
        :returns: Whether the alert has any repeat information.
        """
        return any((self.repeat_days, self.repeat_frequency))

    def reset_repeat(self):
        """
        Resets the expiration time to the last expiration (or to the 
        time of creation if no repeat information is present).
        Mostly used to reschedule recurring alerts to set a new
        start point to calculate from
        """
        expiration = self.expiration
        if self.repeat_days:
            while expiration > self.now or (Weekdays(expiration.weekday()) not in self.repeat_days):
                expiration -= dt.timedelta(days=1)
            self._data["next_expiration_time"] = expiration.isoformat()
        elif self.repeat_frequency:
            expiration = expiration - self.repeat_frequency
            self._data["next_expiration_time"] = expiration.isoformat()

    def remove_repeat(self) -> None:
        """
        Purges repeat information
        """
        self._data["repeat_frequency"] = None
        self._data["repeat_days"] = None
        self._data["until"] = None

    @property
    def until(self) -> Optional[dt.datetime]:
        """
        :returns: The datetime the event (or the repeat mechanism thereof) ends.
        """
        end = self._data.get("until")
        return dt.datetime.fromisoformat(end) if end else None

    @until.setter
    def until(self, end: Union[dt.datetime, dt.timedelta]) -> None:
        if self.expiration is None:
            raise Exception("You can't set an until without expiration")

        # relative to expiration
        if isinstance(end, dt.timedelta):
            self._data["until"] = (self.expiration + end).isoformat()
        elif isinstance(end, dt.datetime):
            self._data["until"] = end.isoformat()
        else:
            raise TypeError("until must be a datetime or timedelta object")

    # Media associated
    @property
    def audio_file(self) -> Optional[str]:
        """
        Returns the audio filename launched on expiration
        """
        return self._data.get("audio_file")

    @property
    def ocp_request(self) -> str:
        """
        OVOS Common Play search string that is set when requesting a music
        alarm
        """
        return self._data.get("ocp")

    @ocp_request.setter
    def ocp_request(self, request: Union[dict, None]):
        if not isinstance(request, (dict, type(None))):
            raise TypeError("'request' is supposed to be of type dict")
        self._data["ocp"] = request

    @property
    def media_type(self):
        """
        Returns the media assosiated with the alert
        :returns: string of the voc name
        """
        if self.ocp_request:
            return "ocp"
        elif self.audio_file:
            return "audio_file"
        return None

    @property
    def media_source(self):
        """
        Returns the media assosiated with the alert
        :returns: string of the voc name
        """
        if self.ocp_request:
            return self.ocp_request
        elif self.audio_file:
            return self.audio_file
        return None

    # DAV properties
    @property
    def service(self) -> Optional[str]:
        """
        DAV Service the alert is associated with
        """
        return self._data.get("dav_service", "")

    @service.setter
    def service(self, service):
        self._data["dav_service"] = service

    @property
    def calendar(self) -> Optional[str]:
        """
        DAV Calendar the alert is associated with
        """
        return self._data.get("dav_calendar", "")

    @calendar.setter
    def calendar(self, calendar):
        self._data["dav_calendar"] = calendar

    @property
    def synchronized(self) -> bool:
        """
        State of DAV synchronicity
        """
        return self._data.get("dav_synchron", False)

    @synchronized.setter
    def synchronized(self, sync: bool):
        if not isinstance(sync, bool):
            raise ValueError("'synchronized' property is supposed to be type bool")
        self._data["dav_synchron"] = sync

    @property
    def skip_sync(self) -> bool:
        """
        Whether the alert should be skipped during DAV synchronization
        """
        return self._data.get("skip_sync", False)

    @skip_sync.setter
    def skip_sync(self, skip: bool):
        if not isinstance(skip, bool):
            raise ValueError("'skip_sync' property is supposed to be type bool")
        self._data["skip_sync"] = skip

    def add_context(self, ctx: dict) -> None:
        """
        Add the requested context to the alert, conflicting values will be
        overwritten with the new context.
        :param ctx: new context to add to alert
        """
        self._data["context"] = merge_dict(self.context, ctx)

    def add_child(self, ident: str = None) -> str:
        """
        Adds a child alert uuid to the context.
        :param ident: the id (uuid) of the child
        """
        ident = ident or str(uuid4())
        if not self.children:
            self._data["context"]["parent_to"] = []
        if ident not in self.children:
            self.children.append(ident)
            self.children.sort()
        return ident

    def remove_child(self, ident: str) -> None:
        """
        Removes a child alert uuid from the context
        :param ident: the id (uuid) of the child
        """
        context = self.context.get("parent_to")
        if context and not ident in context:
            return
        context.remove(ident)

    def set_parent(self, ident: str = None) -> str:
        """
        Sets a parent alert uuid
        :param ident: the id (uuid) of the parent
        """
        ident = ident or str(uuid4())
        self.context["related_to"] = ident
        return ident

    def remove_parent(self, ident: str):
        """
        Removes the parent alert uuid
        :param ident: the id (uuid) of the parent
        """
        if ident == self.context.get("related_to"):
            self.context.pop("related_to")

    def advance(self):
        """
        Advances the expiration the next following date.
        One time alerts expiration will be set to `None`
        """
        return self._get_next_expiration_time(skip=True)

    def _get_next_expiration_time(self, skip=False) -> Optional[dt.datetime]:
        """
        Determine the next time this alert will expire and update Alert data
        """
        # Alarm has no expiration time
        if not self._data.get("next_expiration_time", False):
            return None

        expiration = dt.datetime.fromisoformat(self._data.get("next_expiration_time"))
        now = dt.datetime.now(expiration.tzinfo) if not skip else expiration

        # Alert hasn't expired since last update
        if now < expiration:
            return expiration

        # Alert expired, get next time
        if self.repeat_frequency:
            while expiration <= now:
                expiration += self.repeat_frequency
        elif self.repeat_days:
            # walked on the wall clock of the alert's own zone: a 07:30 alarm
            # rings at 07:30 on either side of a daylight-saving change, which
            # adding 24 hours to a fixed offset would not do
            zone = ZoneInfo(self.timezone_name)
            local = expiration.astimezone(zone)
            # the intended time-of-day is fixed at the alert's own creation
            # and never re-derived from a later occurrence, so a DST gap that
            # forces a one-day shift (e.g. a 01:30 alarm landing on 02:30 the
            # day the clock jumps) does not stick on every following day
            time_of_day = self._data.setdefault(
                "repeat_time_of_day", local.time().isoformat())
            intended = dt.time.fromisoformat(time_of_day)
            while (
                    local <= now
                    or Weekdays(local.weekday()) not in self.repeat_days
            ):
                local = dt.datetime.combine(
                    local.date() + dt.timedelta(days=1), intended
                ).replace(tzinfo=zone)
            expiration = local
        elif self.until is not None:
            while expiration <= now:
                expiration += dt.timedelta(days=1)
        else:
            # Alert expired with no repeat
            return None
        if self.until and expiration > self.until:
            # This alert is expired
            return None
        self._data["next_expiration_time"] = expiration.isoformat()
        LOG.debug(f"New expiration set for {self.ident}({self.alert_name}): {expiration}")
        return expiration

    # Constructors
    @staticmethod
    def from_dict(alert_data: dict):
        """
        Parse a dumped alert dict into an Alert object
        :param alert_data: dict as returned by `Alert.data`
        """
        return Alert(alert_data)

    @staticmethod
    def from_ical(event: List[tuple]):
        """
        Parse the properties of an caldav icalendar instance into an Alert object
        :param alert_data: dict as returned by `Alert.data`
        """
        if event[0] == ("BEGIN", b"VTODO"):
            data = process_ical_todo(event)
        else:
            data = process_ical_event(event)

        # imported outside of any bus message, often on a background sync
        # worker thread that may still be carrying a stale message from
        # whatever it last handled; an explicit empty context keeps a CalDAV
        # alert from inheriting the DAV-configurer's session
        return Alert.create(message_context={}, **data)

    def to_ical(self) -> icalendar.Calendar:
        """
        Creates an icalendar Calendar object of the alert that can by synced
        to DAV.
        :returns: icalendar.Calendar
        """
        ical = icalendar.Calendar()
        expiration = self.expiration

        if self.dav_type == DAVType.VEVENT:
            component = icalendar.Event()
            alarm = icalendar.Alarm()
        elif self.dav_type == DAVType.VTODO:
            component = icalendar.Todo()

        component.add("created", self.created)
        component.add("uid", self.ident)
        component.add("summary", self.alert_name)
        component.add("priority", self.priority)

        if self.dav_type == DAVType.VEVENT:
            end = self.until or expiration
            if self.is_all_day:
                expiration = expiration.date()
                end = expiration + dt.timedelta(days=1)
            component.add("dtstart", expiration, {"tzid": TZID})
            component.add("dtend", end, {"tzid": TZID})
            prenotification = (
                dt.timedelta(seconds=self._data.get("prenotification"))
                if self.prenotification
                else dt.timedelta(0)
            )
            alarm.add("trigger", prenotification)
            alarm.add("action", "DISPLAY")

            component.add_component(alarm)

        elif self.dav_type == DAVType.VTODO:
            if expiration:
                component.add("due", expiration)
            if self.related_to:
                component.add("related-to", self.related_to)
            component.add("status", "NEEDS-ACTION")

        ical.add_component(component)

        return ical

    @staticmethod
    def deserialize(alert_str: str):
        """
        Parse a serialized alert into an Alert object
        :param alert_str: str returned by `Alert.serialize`
        """
        data = json.loads(alert_str)
        return Alert(data)

    @staticmethod
    def create(
            expiration: Union[dt.date, dt.datetime, str] = None,
            prenotification: int = None,
            alert_name: str = None,
            alert_type: AlertType = AlertType.UNKNOWN,
            dav_type: DAVType = DAVType.VEVENT,
            priority: int = AlertPriority.AVERAGE.value,
            repeat_frequency: Union[int, dt.timedelta] = None,
            repeat_days: Set[Weekdays] = None,
            until: Union[dt.datetime, str] = None,
            audio_file: str = None,
            dav_calendar: str = None,
            dav_service: str = None,
            context: dict = None,
            message_context: dict = None,
            lang: str = None,
            timezone: str = None
    ):
        """
        Object representing an arbitrary alert
        :param expiration: datetime representing first alert expiration
        :param prenotification: negative delta to expiration in seconds
        :param alert_name: human-readable name for this alert
        :param alert_type: type of alert (i.e. alarm, timer, reminder)
        :param priority: int priority 1-10
        :param repeat_frequency: time in seconds between alert occurrences
        :param repeat_days: set of weekdays for an alert to repeat
        :param until: datetime of final repeat/end of event
        :param audio_file: audio_file to playback on alert expiration
        :param context: Message context associated with alert
        :param message_context: the creating message's bus context (session,
            source, destination, etc.), held verbatim and handed back to the
            scheduler on every re-offer so a restart does not strip the
            creating satellite's routing identity from the schedule.
        :param timezone: IANA zone a weekday repeat is read in, defaulting
            to the configured one
        """
        from .parse_utils import get_default_alert_name

        data = dict()

        if expiration:
            if isinstance(expiration, str):
                expiration = dt.datetime.fromisoformat(expiration)
            elif expiration.__class__ == dt.date:
                data["all_day"] = True
                expiration = dt.datetime.combine(expiration, dt.time.min) \
                    .replace(tzinfo=get_default_tz())
            if not expiration.tzinfo:
                raise ValueError("expiration missing tzinfo")
            # Round off any microseconds
            expiration = expiration.replace(microsecond=0)
        if until:
            if data.get("all_day"):
                until = expiration.replace(hour=23, minute=59, second=59)
            elif isinstance(until, str):
                until = dt.datetime.fromisoformat(until)
            if not until.tzinfo:
                raise ValueError("expiration missing tzinfo")
            # Round off any microseconds
            until = until.replace(microsecond=0)
        if isinstance(prenotification, dt.timedelta):
            # Convert timedelta to negative int
            prenotification = int(prenotification.total_seconds())
            if prenotification > 0:
                prenotification *= -1
        if isinstance(repeat_frequency, dt.timedelta):
            # Convert timedelta to int
            repeat_frequency = (
                round(repeat_frequency.total_seconds()) if repeat_frequency else None
            )

        # Convert repeat_days to int representation
        repeat_days = [d.value for d in repeat_days] if repeat_days else None

        # Enforce and Default Values
        if alert_name is None:
            if data.get("all_day"):
                alert_name = get_default_alert_name(expiration.date(), alert_type)
            else:
                alert_name = get_default_alert_name(expiration, alert_type)
        if alert_type == AlertType.TODO:
            dav_type = DAVType.VTODO

        if context is None:
            context = dict()
        if not context.get("created"):
            context["created"] = time()
        if not context.get("ident"):
            context["ident"] = str(uuid4())

        data.update({
            "next_expiration_time": expiration.isoformat() if expiration else None,
            "prenotification": prenotification,
            "alert_type": alert_type.value,
            "dav_type": dav_type.value,
            "priority": priority,
            "repeat_frequency": repeat_frequency,
            "repeat_days": repeat_days,
            "until": until.isoformat() if until else None,
            "alert_name": alert_name,
            "audio_file": audio_file,
            "context": context,
            "message_context": message_context or dict(),
            "dav_calendar": dav_calendar,
            "dav_service": dav_service,
            "dav_synchron": False,
        })
        data["lang"] = lang or get_default_lang()
        data["timezone"] = timezone or TZID
        return Alert(data)


def is_alert_type(alert: Alert, alert_type: AlertType) -> bool:
    """
    Check if an alert is of a given type
    :param alert: Alert object
    :param alert_type: AlertType
    :returns: bool
    """
    if alert_type == AlertType.ALL:
        return True

    return alert.alert_type == alert_type.value


def properties_changed(local: Alert, dav: Alert) -> bool:
    """
    Helper to check if the properties of a local reminder differs from that of a DAV event
    (i.e. changes were made upstream)
    Note: Local changes gets synced right away
    """
    if local.alert_name != dav.alert_name:
        LOG.debug(f"name changed ({dav.alert_name})")
    if local.expiration != dav.expiration:
        LOG.debug(f"expiration changed ({dav.alert_name})")
    if local.prenotification != dav.prenotification:
        LOG.debug(f"prenotification changed ({dav.alert_name})")
    if local.children != dav.children:
        LOG.debug(f"list entries changed ({dav.alert_name})")
    if local.until != dav.until:
        LOG.debug(f"event length changed ({dav.alert_name})")
    return any(
        [
            local.alert_name != dav.alert_name,
            local.expiration != dav.expiration,
            local.prenotification != dav.prenotification,
            local.children != dav.children,
            local.until != dav.until
        ]
    )
