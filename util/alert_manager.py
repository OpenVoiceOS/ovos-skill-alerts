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
import os
from uuid import uuid4
from copy import deepcopy
from typing import List, Dict, Tuple, Optional, Union, Any

from dateutil.relativedelta import relativedelta
import caldav
from caldav.lib.error import NotFoundError
from combo_lock import NamedLock
from json_database import JsonStorage
from ovos_bus_client.message import Message
from ovos_utils.log import LOG

from ovos_skill_alerts.util import AlertState, AlertType, DAVType, LOCAL_USER
from ovos_skill_alerts.util.alert import Alert, alert_time_in_range, is_alert_type, properties_changed
from ovos_skill_alerts.util.dav_utils import get_dav_items, DAVCredentials
from ovos_skill_alerts.util.parse_utils import get_default_alert_name, has_default_name

SYNC_LOCK = NamedLock("alert_dav_sync")

_ALERTFILE = "alerts.json"
_SYNC_RESTRICTED = (AlertType.TIMER, AlertType.ALARM, AlertType.UNKNOWN, AlertType.ALL)
#: schedules of this skill that do not belong to any one alert
_HOUSEKEEPING_IDS = frozenset(("alerts.sync_dav", "check_active_state"))
#: where the scheduler reports the occurrences it could not deliver on time
SCHEDULER_MISSED = "ovos.scheduler.missed"
#: an occurrence delivered later than this is an alert that was missed rather
#: than one to ring, mirroring the scheduler's own default grace period
MISSED_AFTER = dt.timedelta(seconds=60)
#: the period a wall-clock repeat is carried by. Such an alert is moved to its
#: real next occurrence every time it fires, and a recurrence is what it is
#: held as because a spent single occurrence is retired by the scheduler once
#: the handler it called returns, which would take the replacement with it.
_CARRIER_PERIOD = 24 * 60 * 60



def sort_alerts_list(alerts: List[Alert]) -> List[Alert]:
    """
    Sort the passed list of alerts by time of next expiration,
    chronologically ascending. Allows None sorting (to the end).
    :param alerts: list of Alert objects to sort
    :returns: sorted list of alerts
    """
    alerts.sort(
        key=lambda alert: (
            alert.expiration is None,
            alert.expiration or None,
        )
    )
    return alerts


def get_alerts_by_type(alerts: List[Alert]) -> dict:
    """
    Parse a list of alerts into a dict of alerts by alert type.
    :param alerts: list of Alert objects to organize
    :returns: dict of AlertType to list of alerts
    """
    sorted_dict = dict()
    for alert in AlertType:
        sorted_dict.setdefault(alert, list())
    for alert in alerts:
        key = alert.alert_type
        sorted_dict[key].append(alert)

    return sorted_dict


class AlertManager:
    def __init__(self,
                 home_path: str,
                 skill,
                 skill_callbacks: Tuple[callable]):
        """
        :param skill: the skill this manager belongs to. Alert timing is asked
            for through the skill's scheduling methods; the manager never
            speaks to the scheduler itself.
        """
        self._home = home_path
        self._alerts_store = JsonStorage(os.path.join(home_path, _ALERTFILE))
        self._skill = skill
        self._callback_prenotify, self._callback_expiration = skill_callbacks
        self._pending_alerts = dict()
        self._missed_alerts = dict()
        self._active_alerts = dict()
        self._synchron_ids = set()
        self._read_lock = NamedLock("alert_manager")
        self._active_gui_timers : List[Alert] = list()
        self._dav_clients = dict()

        self._load_cache()
        if self._skill.bus:
            self._skill.bus.on(SCHEDULER_MISSED, self._handle_missed_occurrence)
        self.reschedule_pending_alerts()

    @property
    def active_gui_timers(self) -> List[Alert]:
        with self._read_lock:
            return deepcopy(self._active_gui_timers)

    @property
    def missed_alerts(self) -> dict:
        """
        Returns a static dict of current missed alerts
        """
        with self._read_lock:
            return deepcopy(self._missed_alerts)

    @property
    def pending_alerts(self) -> dict:
        """
        Returns a static dict of current pending alerts
        """
        with self._read_lock:
            return deepcopy(self._pending_alerts)

    @property
    def active_alerts(self) -> dict:
        """
        Returns a static dict of current active alerts
        """
        with self._read_lock:
            return deepcopy(self._active_alerts)

    @property
    def active_ids(self) -> set:
        """
        Returns a set of active alert uuids
        """
        return set(self.active_alerts.keys())

    @property
    def pending_ids(self) -> set:
        """
        Returns a set of pending alert uuids
        """
        return set(self.pending_alerts.keys())

    @property
    def missed_ids(self) -> set:
        """
        Returns a set of missed alert uuids
        """
        return set(self.missed_alerts.keys())

    @property
    def synchron_ids(self) -> set:
        """
        Returns a set of dav synchron uuids
        """
        return self._synchron_ids

    @property
    def dav_active(self) -> bool:
        """
        Returns whether DAV was fully initialised
        """
        return any(self._dav_clients.values())

    @property
    def dav_services(self) -> list:
        """
        Returns a list of active DAV services
        """
        return list(self._dav_clients.keys())

    @property
    def dav_calendars(self) -> list:
        """
        Returns a list of dav calendar names available on DAV
        """
        return [
            cal for calendars in self.get_calendar_names().values() for cal in calendars
        ]

    def init_dav_clients(
        self, services: list, frequency: int, test_connectivity: bool = True
    ) -> Dict[str, List[str]]:
        """
        Creates dav clients from the credential dict specified
        :param services: list of services to initialize
        :param frequency: minutes between sync events
        :param test_connectivity: whether to test the connectivity (optional)
        :returns: errors (dict conataining dialog/services pairs) to be voiced
        """
        client = None
        _credentials = DAVCredentials(self._home, services)
        errors = {"dav_credentials_missing": [], "dav_service_cant_connect": []}
        # no DAV clients
        if _credentials.empty:
            return errors
        
        for service in services:
            if not _credentials.viable(service):
                errors["dav_credentials_missing"].append(service)
                continue
            client = caldav.DAVClient(**_credentials[service])
            if test_connectivity:
                try:
                    client.principal()
                except Exception as e:
                    errors["dav_service_cant_connect"].append(service)
                    LOG.error(
                        (
                            f"DAV Service {_credentials[service]['url']} "
                            f"isn't reachable. Exception: {str(e)}"
                        )
                    )
                    continue
            self._dav_clients[service] = client

        if self.dav_active:
            self._skill.schedule_repeating_event(self.sync_dav, None,
                                                 frequency * 60,
                                                 name="alerts.sync_dav")
            LOG.debug("Sync event started")

        return errors

    # Query Methods
    def get_alert_status(self, alert_id: str) -> Optional[AlertState]:
        """
        Get the current state of the requested alert_id. If a repeating alert
        exists in multiple states, it will report in priority order:
        ACTIVE, MISSED, PENDING
        :param alert_id: ID of alert to query
        :returns: AlertState of the requested alert or None if alert not found
        """
        if alert_id in self._missed_alerts:
            return AlertState.MISSED
        if alert_id in self._active_alerts:
            return AlertState.ACTIVE
        if alert_id in self._pending_alerts:
            return AlertState.PENDING
        return AlertState.REMOVED

    def get_alert(self, alert_id: str) -> Alert:
        """
        Get a Alert opbject by ident. 
        :param alert_id: ID of alert to query
        :returns: Alert opbject/object data
        """
        alert = None
        with self._read_lock:
            if alert_id in self._active_alerts:
                alert = self._active_alerts.get(alert_id)
            elif alert_id in self._missed_alerts:
                alert = self._missed_alerts.get(alert_id)
            elif alert_id in self._pending_alerts:
                alert = self._pending_alerts.get(alert_id)
            else:
                LOG.error(f"{alert_id} not found")
        return alert

    def get_alerts(self, user: str = "",
                         alert_type: AlertType = AlertType.ALL) \
        -> Dict[str, List[Alert]]:
        """
        Get a sorted list of all managed alerts.
        :returns: dict of disposition to sorted alerts for all users
        """
        with self._read_lock:
            missed = self.get_missed_alerts(user, alert_type)
            active = self.get_active_alerts(user, alert_type)
            pending = self.get_pending_alerts(user, alert_type)

        return {
            "missed": missed,
            "active": active,
            "pending": pending
        }
    
    def get_pending_alerts(self, user: str = "",
                                 alert_type: AlertType = AlertType.ALL) \
        -> List[Alert]:
        """
        Return a list of pending alerts
        Optionally restrict this list by user and/or type
        """
        pending = sort_alerts_list([alert for alert in
                                    self._pending_alerts.values()])
        if user:
            pending = list(filter(lambda x: x.user == user, pending))
        
        if alert_type != AlertType.ALL:
            pending = list(filter(lambda x: x.alert_type == alert_type, pending))

        return pending
    
    def get_active_alerts(self, user: str = "",
                                alert_type: AlertType = AlertType.ALL)\
        -> List[Alert]:
        """
        Return a list of active alerts
        Optionally restrict this list by user and/or type
        """
        active = sort_alerts_list([alert for alert in
                                   self._active_alerts.values()])
        if user:
            active = list(filter(lambda x: x.user == user, active))
        
        if alert_type != AlertType.ALL:
            active = list(filter(lambda x: x.alert_type == alert_type, active))

        return active

    def get_missed_alerts(self, user: str = "",
                                alert_type: AlertType = AlertType.ALL) \
        -> List[Alert]:
        """
        Return a list of missed alerts
        Optionally restrict this list by user and/or type
        """
        missed = sort_alerts_list([alert for alert in
                                   self._missed_alerts.values()])
        if user:
            missed = list(filter(lambda x: x.user == user, missed))
        
        if alert_type != AlertType.ALL:
            missed = list(filter(lambda x: x.alert_type == alert_type, missed))

        return missed
        
    def get_alerts_in_timeframe(self,
                                t1: Optional[dt.datetime],
                                t2: Optional[dt.datetime] = None,
                                alert_type = AlertType.EVENT) -> List[Alert]:
        """
        Get a list of alert (reminder) objects which are overlapping
        with the datetime(s) passed
        :param t1: expiration datetime of the event
        :param t1: expiration datetime of the event
        :param alert_type: expiration datetime of the event
        :returns List of alert objects
        """
        # TODO exclude multiday?
        if not isinstance(t1, dt.datetime):
            return []
        with self._read_lock:
            overlapping = [
                alert
                for alert in self._pending_alerts.values()
                if is_alert_type(alert, alert_type)
                and alert_time_in_range(t1, t2, alert.expiration, alert.until)
            ]
        return overlapping

    def get_connected_alerts(self, user: str = None, type: AlertType = None) \
        -> List[Alert]:
        """
        Return a list of connected alerts (ie the alert has a child alert)
        Optionally restrict this list by user and/or type
        """
        alerts = self.get_alerts(user, type)["pending"]
        return list(filter(lambda alert: alert.children, alerts))
    
    def get_unconnected_alerts(self, user: str = None, type: AlertType = None) \
        -> List[Alert]:
        """
        Return a list of unconnected alerts (ie the alert has no child and 
        parent alert)
        Optionally restrict this list by user and/or type
        """
        alerts = self.get_alerts(user, type)["pending"]
        return list(
            filter(
                lambda alert: not alert.children and not alert.related_to, alerts
            )
        )

    def get_children(self, ident: str) -> List[Alert]:
        """
        Get a list of alert objects which are children of the specified ident
        :param ident: identification uuid
        :returns List of alert objects
        """
        with self._read_lock:
            children = [
                alert
                for alert in self._pending_alerts.values()
                if alert.related_to == ident
            ]
        return children

    def get_parents(self, uid) -> List[Alert]:
        """
        Get a list of alert objects which are parents of the specified ident
        :param ident: identification uuid
        :returns List of alert objects
        """
        with self._read_lock:
            parents = [
                alert
                for alert in self._pending_alerts.values()
                if uid in alert.children
            ]
        return parents

    # Alert Management
    def mark_alert_missed(self, alert_id: str) -> None:
        """
        Mark an active alert as missed
        :param alert_id: ident of active alert to mark as missed
        """
        LOG.debug(f"mark alert missed: {alert_id}")
        try:
            with self._read_lock:
                self._missed_alerts[alert_id] = self._active_alerts.pop(alert_id)
            self.dismiss_alert_from_gui(alert_id)
            self._dump_cache()
        except KeyError:
            LOG.error(f"{alert_id} is not active")

    def mark_alert_synchron(self, alert: Alert) -> None:
        """
        Mark an alert as synchron (with DAV)
        :param alert: alert to be marked as snychron
        """
        alert.synchronized = True
        self._synchron_ids.add(alert.ident)

    def remove_synchron_state(self, alert: Alert) -> None:
        """
        Remove the synchron flag from an alert.
        :param alert: alert to be marked as not snychron
        """
        if alert.ident in self._synchron_ids:
            self._synchron_ids.remove(alert.ident)
        alert.synchronized = False
        
    def snooze_alert(self, alert_id: str,
                           snooze_duration: dt.timedelta) -> Alert:
        """
        Snooze an active or missed alert for some period of time.
        :param alert_id: ID of active or missed alert to snooze
        :param snooze_duration: time until next notification
        :returns: New Alert added to pending
        """
        alert = None
        with self._read_lock:
            if alert_id in self._active_alerts:
                alert: Alert = self._active_alerts.pop(alert_id)
            elif alert_id in self._missed_alerts:
                alert: Alert = self._missed_alerts.pop(alert_id)
        if not alert:
            raise KeyError(f'No missed or active alert with ID: {alert_id}')

        ident = alert.ident
        if not ident.startswith("snoozed"):
            alert.add_context({"ident": f'snoozed_{ident}'})

        alert.expiration = dt.datetime.now(alert.timezone) + snooze_duration

        if alert.alert_type == AlertType.TIMER:
            self.add_timer_to_gui(alert)
            self.dismiss_alert_from_gui(ident)

        LOG.info((f"Snoozed {alert.alert_type.name} ({alert.alert_name})"
                  f" for {snooze_duration}"))
        self.add_alert(alert)

        return alert
    
    def reschedule_alert(self, old_alert: Alert,
                               new_expiration: Optional[Union[dt.date, dt.datetime, dt.timedelta, relativedelta]] = None,
                               once = False):
        """
        Manages a rescheduled alert
        If no new expiration is passed, the alert is rescheduled on the expiration set in the alert.
        In case of a repeating alert `once` can be set to reschedule only the next alert. 

        :param old_alert: alert to be rescheduled
        :param new_expiration: (optional) new expiration time
        :param once: (default: False) whether the alert should be rescheduled once
        :param 
        """
        self.rm_alert(old_alert.ident,
                      AlertState.PENDING)  # alert.alert_type not in _SYNC_RESTRICTED

        name = old_alert.alert_name
        default_naming = has_default_name(old_alert)
        new_expiration = new_expiration or \
                dt.datetime.fromisoformat(old_alert._data["next_expiration_time"])
        old_alert_copy = deepcopy(old_alert)

        if once and old_alert.has_repeat:
            new_alert = old_alert_copy
            # advance the (old) alert and readd it
            old_alert.advance()
            if old_alert.expiration is not None:
                self.add_alert(old_alert)
                self.sync_dav_item(old_alert)

            # set rescheduled alert to non-recurring
            new_alert.remove_repeat()
            new_alert.add_context({"ident": str(uuid4())})
        else:
            new_alert = old_alert
        
        if isinstance(new_expiration, (dt.timedelta, relativedelta,)):
            new_expiration = new_alert.expiration + new_expiration
        LOG.info((f"Rescheduled {new_alert.alert_type.name}: {name}"
                f" ({old_alert.ident}) to {new_expiration}"))
        # adjust name if default
        if default_naming:
            new_alert._data["alert_name"] = get_default_alert_name(new_expiration,
                                                                   new_alert.alert_type,
                                                                   now_time=new_alert.created)
        new_alert.expiration = new_expiration
        self.add_alert(new_alert)
        self.sync_dav_item(new_alert)

        if new_alert.alert_type == AlertType.TIMER:
            self.add_timer_to_gui(new_alert)

        return new_alert
        
    def reschedule_repeat(self, alert: Alert,
                          new_repeat: Union[dt.timedelta, set]):

        alert.reset_repeat()
        if isinstance(new_repeat, set):
            alert._data["repeat_days"] = new_repeat
        elif isinstance(new_repeat, dt.timedelta):
            alert._data["repeat_frequency"] = round(new_repeat.total_seconds())
        
        self.reschedule_alert(alert)
        return alert.expiration
        
    def add_alert(self, alert: Alert) -> str:
        """
        Add an alert to the scheduler and return the alert ID
        :returns: string identifier for the scheduled alert
        """
        # TODO: Consider checking ident is unique
        # TODO: force reset synchro flag? by now only if removed
        ident = alert.ident or str(uuid4())
        alert.add_context({"ident": ident})  # ensure ident is set 
        if alert.expiration:
            self._schedule_alert(alert, ident)
        if alert.prenotification:
            self._schedule_alert(alert, ident, "prenotification")
        if alert.related_to:
            parent = self.get_alert(alert.related_to)
            parent.add_child(alert.ident)
        with self._read_lock:
            self._pending_alerts[ident] = alert
        self._dump_cache()
        return ident

    def rm_alert(self, alert_id: str,
                 disposition: AlertState = None,
                 drop_dav = False):
        """
        Remove an alert with given disposition (pending/active/missed).
        If no disposition is passed it is searched in the database.
        Drops dav content (default=False) if DAV connection is active

        :param alert_id: ident of active alert to remove
        :param disposition: (pending/active/missed) alert, default pending
        :param drop_dav: whether to drop the item on DAV
        """
        disposition = disposition or self.get_alert_status(alert_id)
        if disposition == AlertState.REMOVED:
            LOG.error(f"{alert_id} is already removed")
            return None
        elif disposition == AlertState.MISSED:
            alerts = self._missed_alerts
        elif disposition == AlertState.ACTIVE:
            alerts = self._active_alerts
        elif disposition == AlertState.PENDING:
            alerts = self._pending_alerts
        else:
            LOG.error(f"Unknown disposition: {disposition}")
            return None

        with self._read_lock:
            try:
                removed_alert: Alert = alerts.pop(alert_id)
            except KeyError:
                LOG.error(f"No alert with disposition {disposition}")
                return None
            
            #self.dismiss_alert_from_gui(alert_id)
        LOG.info((f"Removing {disposition.name} {removed_alert.alert_type.name}:"
                  f" {removed_alert.alert_name} ({alert_id})"))

        if removed_alert.has_expiration:
            self._cancel_scheduled_event(removed_alert)
        if removed_alert.related_to:
            parents = self.get_parents(alert_id)
            for alert in parents:
                alert.remove_child(alert_id)
        if removed_alert.synchronized:
            self.remove_synchron_state(removed_alert)
            if drop_dav:
                self.drop_dav_item(removed_alert)
        self._dump_cache()
        return removed_alert

    def add_timer_to_gui(self, alert: Alert):
        """
        Add a timer to the GUI.
        :param alert: Timer to add to GUI
        """
        for i, pending in enumerate(self._active_gui_timers):
            # TODO this shouldnt work
            if pending == alert:
                self._active_gui_timers[i] = alert
                break
        else:
            self._active_gui_timers.append(alert)
            self._active_gui_timers.sort(
                key=lambda i: i.time_to_expiration.total_seconds())

    def dismiss_alert_from_gui(self, alert_id: str):
        """
        Dismiss an alert from long-lived GUI displays.
        """
        # Active timers are a copy of the original, check by ID
        for pending in self._active_gui_timers:
            if pending.ident == alert_id:
                self._active_gui_timers.remove(pending)
                return True
        return False

    # Alert Event Handlers
    @staticmethod
    def _schedule_name(ident: str, reason: str) -> str:
        """
        The name one alert's timing is known by. The name is the identity a
        schedule is replaced and cancelled by, so it is the alert's own uuid,
        with the prenotification hanging off it.
        """
        return ident if reason == "expiration" else f"{ident}.pre"

    def _schedule_alert(self, alrt: Alert, ident: str, reason: str = "expiration"):
        """
        Ask for the next expiration of an alert to be called back on.

        A fixed period is handed over whole and the scheduler walks it. A
        weekday alarm and an alert with an end date are walked by the alert
        itself, one occurrence at a time: a wall clock is what has to survive
        a daylight-saving change, and a period of seconds is not one.

        :param alrt: Alert object to schedule
        :param ident: Unique identifier associated with the Alert
        """
        name = self._schedule_name(ident, reason)
        data = dict(alrt.data, alert_reason=reason)
        # Re-offering an alert (eg on skill load) happens with no message in
        # flight, so the scheduling methods would otherwise fall back to an
        # empty context and replace the stored record's routing identity
        # (session/source of the satellite that created it) with none at
        # all. The creating message's context is held on the alert itself
        # and handed back explicitly so a restart cannot strip it.
        #
        # A CalDAV import is the one alert with nothing to hand back: it
        # was never created from a bus message, so a falsy context here
        # would send the scheduling call looking for one on its own, via
        # `dig_for_message`, which walks the call stack rather than a
        # thread-local and so picks up whatever intent handler's `Message`
        # a DAV sync happens to be running inside (e.g. the one that
        # configured the calendar). The alert's own small, session-free
        # context is handed over instead, which is non-empty and therefore
        # blocks that fallback.
        context = alrt.message_context or (
            alrt.context if (alrt.calendar or alrt.service) else None)
        if reason == "prenotification":
            LOG.debug(f"Scheduling alert {reason}: {ident} ({alrt.alert_name})"
                      f" at {alrt.prenotification}")
            self._skill.schedule_event(self._handle_alert_expiration,
                                       alrt.prenotification, data, name=name,
                                       context=context)
        elif alrt.repeat_frequency:
            LOG.debug(f"Scheduling alert {reason}: {ident} ({alrt.alert_name})"
                      f" every {alrt.repeat_frequency}")
            self._skill.schedule_repeating_event(
                self._handle_alert_expiration, alrt.expiration,
                round(alrt.repeat_frequency.total_seconds()), data, name=name,
                context=context)
        elif alrt.repeat_days or alrt.until:
            LOG.debug(f"Scheduling alert {reason}: {ident} ({alrt.alert_name})"
                      f" next at {alrt.expiration}")
            self._skill.schedule_repeating_event(
                self._handle_alert_expiration, alrt.expiration,
                _CARRIER_PERIOD, data, name=name, context=context)
        else:
            LOG.debug(f"Scheduling alert {reason}: {ident} ({alrt.alert_name})"
                      f" at {alrt.expiration}")
            self._skill.schedule_event(self._handle_alert_expiration,
                                       alrt.expiration, data, name=name,
                                       context=context)

    def _cancel_scheduled_event(self, alert: Alert) -> None:
        """
        Remove the scheduler event(s) of a specific alert
        :param alert: Alert object to remove
        """
        for reason in ("expiration", "prenotification"):
            self._skill.cancel_scheduled_event(
                self._schedule_name(alert.ident, reason))

    def _handle_alert_expiration(self, message: Message):
        """
        Called upon expiration of an alert. Updates internal references, checks
        for repeat cases, and calls the specified callback.
        :param message: Message associated with expired alert
        """
        scheduler = message.context.get("scheduler") or dict()
        name = scheduler.get("id") or message.context.get("ident") or \
            message.data.get("context", {}).get("ident", "")
        alert_id = name[:-len(".pre")] if name.endswith(".pre") else name
        reason = message.data.get("alert_reason") or \
            message.context.get("alert_reason")
        alert_name = message.data.get("alert_name")

        alert = self._pending_or_reported_missed(alert_id)
        if alert is None:
            LOG.error("No pending alert present to handle expiration")
            return

        # sending a deepcopy to the subsequent handlers
        # deepcopy as early as possible to avoid alert.expiration calls
        alert_cpy = deepcopy(alert)
        alert_cpy.remove_repeat()

        LOG.debug(f'alert {reason}: {alert_id} ({alert_name})')
        if reason == "expiration":
            if not self._is_due(alert, scheduler):
                # the recurrence carrying a wall-clock repeat came round
                # before the alert did; there is nothing to ring yet
                self._reschedule(alert, alert_id)
                return
            self._active_alerts[alert_id] = alert_cpy
            self._advance_or_drop(alert, alert_id)
            if self._delivered_late(scheduler):
                # the assistant was not there to ring at the time, and an
                # alarm going off long after it was due is worse than one that
                # is reported as missed
                LOG.info(f"Alert {alert_id} was delivered too late to ring")
                self.mark_alert_missed(alert_id)
                return
            self._callback_expiration(alert_cpy)
        elif reason == "prenotification":
            self._active_alerts[alert_id] = alert_cpy
            self._callback_prenotify(alert)
        else:
            LOG.error(f"Couldn't handle context 'alert_reason': {reason}")

    def _pending_or_reported_missed(self, alert_id: str) -> Optional[Alert]:
        """
        The pending alert an occurrence belongs to.

        The scheduler reports what it is about to deliver late before it
        delivers it, so an alert may already have been put on the missed list
        by the time its occurrence arrives. The delivery settles it: the
        report was only ever provisional.
        """
        with self._read_lock:
            alert = self._pending_alerts.get(alert_id)
            if alert is None and alert_id in self._missed_alerts:
                alert = self._pending_alerts[alert_id] = \
                    self._missed_alerts.pop(alert_id)
            return alert

    def _advance_or_drop(self, alert: Alert, alert_id: str):
        """
        Move an alert on to its next occurrence, or forget it when it has run
        out of them. A fixed period is already held by the scheduler; a
        wall-clock repeat is moved on here.
        """
        if alert.advance() is None:
            self.rm_alert(alert_id, AlertState.PENDING)
            return
        # only relevant to DAV, so the alert isn't overwritten there
        alert.synchronized = False
        if not alert.repeat_frequency:
            self._reschedule(alert, alert_id)
        if alert.prenotification:
            self._schedule_alert(alert, alert_id, "prenotification")
        self._dump_cache()

    def _reschedule(self, alert: Alert, alert_id: str):
        """
        Move the schedule carrying an alert to the alert's next occurrence.
        """
        self._skill.cancel_scheduled_event(
            self._schedule_name(alert_id, "expiration"))
        self._schedule_alert(alert, alert_id)

    @staticmethod
    def _is_due(alert: Alert, scheduler: dict) -> bool:
        """
        Whether an occurrence is the one the alert is waiting for, rather than
        the recurrence that carries it coming round in between.
        """
        due = scheduler.get("due")
        if not due or alert.expiration is None:
            return True
        return dt.datetime.fromisoformat(due) >= alert.expiration - MISSED_AFTER

    @staticmethod
    def _delivered_late(scheduler: dict) -> bool:
        """
        Whether an occurrence reached this skill so long after it was due that
        it belongs on the missed list instead of ringing.
        """
        due, fired = scheduler.get("due"), scheduler.get("fired")
        if not due or not fired:
            return False
        return dt.datetime.fromisoformat(fired) - \
            dt.datetime.fromisoformat(due) > MISSED_AFTER

    # File Operations
    def _dump_cache(self):
        """
        Write current alerts to the cache on disk. Active alerts are not cached
        """
        with self._read_lock:
            missed_alerts = {ident: alert.serialize for
                             ident, alert in self._missed_alerts.items()}
            pending_alerts = {ident: alert.serialize for
                              ident, alert in self._pending_alerts.items()}
            self._alerts_store["missed"] = missed_alerts
            self._alerts_store["pending"] = pending_alerts
            self._alerts_store.store()

    def _load_cache(self):
        """
        Read alerts from cache on disk. Any loaded alerts will be overwritten.
        """
        # Load cached alerts into internal objects
        with self._read_lock:
            missed = self._alerts_store.get("missed") or dict()
            pending = self._alerts_store.get("pending") or dict()

        if not missed and not pending:
            LOG.debug("No cached data to load")
        else:
            LOG.debug((f"Loading {len(missed.keys())} missed and "
                       f"{len(pending.keys())} pending alerts from cache"))

        # Populate previously missed alerts
        for ident, alert_json in missed.items():
            alert = Alert.deserialize(alert_json)
            with self._read_lock:
                self._missed_alerts[ident] = alert
            if alert.synchronized:
                self._synchron_ids.add(alert.ident)

        # Populate previously pending alerts
        for ident, alert_json in pending.items():
            alert = Alert.deserialize(alert_json)
            if alert.is_expired:  # Alert expired while shut down
                with self._read_lock:
                    self._missed_alerts[ident] = alert
            else:
                with self._read_lock:
                    self._pending_alerts[ident] = alert
                if alert.synchronized:
                    self._synchron_ids.add(alert.ident)
                if alert.alert_type == AlertType.TIMER and \
                        alert.user == LOCAL_USER:
                    LOG.debug(f'Adding timer to GUI: {alert.alert_name}')
                    self._active_gui_timers.append(alert)

    def reschedule_pending_alerts(self):
        """
        Hand this skill's timing back to the scheduler after a restart.

        A schedule outlives the process that asked for it, but the handler it
        calls does not, and a handler is attached by scheduling. Every pending
        alert is therefore offered again under the name it already has, which
        replaces the schedule the scheduler is holding rather than adding a
        second one beside it. A single occurrence keeps the instant it was
        always going to fire at.
        """
        for ident, alert in self.pending_alerts.items():
            if alert.expiration:
                self._schedule_alert(alert, ident)
            if alert.prenotification:
                self._schedule_alert(alert, ident, "prenotification")

    def _handle_missed_occurrence(self, message: Message):
        """
        The scheduler names occurrences it could not deliver on time.

        An alert whose last occurrence went by while nothing was listening is
        one the user missed. A repeating alert keeps its place in the series
        and only loses that occurrence, and an occurrence the scheduler goes
        on to deliver late is settled by the delivery instead.
        """
        schedule_id = message.data.get("id", "")
        if message.data.get("owner") != self._skill.skill_id or \
                schedule_id in _HOUSEKEEPING_IDS or schedule_id.endswith(".pre"):
            return
        undelivered = set(message.data.get("missed") or ()) - \
            set(message.data.get("fired_late") or ())
        if not undelivered or message.data.get("next") is not None:
            return
        with self._read_lock:
            if schedule_id not in self._pending_alerts:
                return
            LOG.info(f"Alert {schedule_id} was due while nothing was listening")
            self._missed_alerts[schedule_id] = \
                self._pending_alerts.pop(schedule_id)
        self._dump_cache()

    def write_cache_now(self):
        """
        Write the current state of the AlertManager to file cache
        """
        self._dump_cache()

    # DAV Operations
    def get_dav_calendar(self, service: str, name: str) -> caldav.objects.Calendar:
        """
        Get Calendar object of the specified DAV service with the specified calendar name
        All operational tasks are called upon this calendar object
        :param service: the service the calendar is associated with
        :param name: the calendar name
        :returns: Calendar object
        """
        calendar = None
        client = self._dav_clients.get(service, None)
        if client:
            principal = client.principal()
            calendar = principal.calendar(name=name)
            calendar.id = service
        return calendar

    def get_dav_calendars(self) -> List[caldav.objects.Calendar]:
        """
        Get all Calendar object of the DAV services initialized
        :returns: list of Calendar objects
        """
        calendars = list()
        for service in self.dav_services:
            client = self._dav_clients.get(service, None)
            if client:
                principal = client.principal()
                # get all available calendars (for this user)
                cals = principal.calendars()
                for c in cals:
                    c.id = service
                calendars.extend(cals)
        return calendars

    def get_calendar_names(self) -> dict:
        """
        Returns all calendar names from across the specified DAV services
        :returns dict of service/calendar names list pairs
        """
        calendars = self.get_dav_calendars()
        calendar_names = dict()
        for calendar in calendars:
            if calendar_names.get(calendar.id, False):
                calendar_names[calendar.id].append(calendar.name)
            else:
                calendar_names[calendar.id] = [calendar.name]
        return calendar_names

    def sync_dav_item(self, alert: Alert) -> None:
        """
        Manually sync an alert with DAV
        Note: Only necessary if it got locally edited (rescheduled, ..),
        as this is not handled by sync_dav
        :param alert: Alert object to be synced
        """
        if any([not self.dav_active,
                alert.alert_type in _SYNC_RESTRICTED,
                alert.skip_sync]):
            return
        
        with SYNC_LOCK:
            calendar = self.get_dav_calendar(alert.service, alert.calendar)
            if alert.dav_type == DAVType.VEVENT:
                try:
                    event_on_dav = calendar.event_by_uid(alert.ident)
                # create new
                except NotFoundError:
                    calendar.save_event(alert.to_ical())
                # overwrite existing
                else:
                    event_on_dav.data = alert.to_ical()
                    event_on_dav.save()                    
            elif alert.dav_type == DAVType.VTODO:
                try:
                    todo_on_dav = calendar.todo_by_uid(alert.ident)
                # create new
                except NotFoundError:
                    calendar.save_todo(alert.to_ical())
                # overwrite existing
                else:
                    todo_on_dav.data = alert.to_ical()
                    todo_on_dav.save()
            self.mark_alert_synchron(alert)

    def drop_dav_item(self, alert: Alert) -> None:
        """
        Drop a specific event that is hosted on a given DAV service
        :param alert: a Alert object to be dropped
        :param subitems: list of uids from Alert(todo) subitems to be dropped
        """
        if alert.calendar is None:
            return

        calendar = self.get_dav_calendar(alert.service, alert.calendar)
        if alert.dav_type == DAVType.VEVENT:
            # might break with some services
            envent_on_dav = calendar.event_by_uid(alert.ident)
            if envent_on_dav:
                LOG.debug(f"Removing VEVENT ({alert.alert_name}) from DAV")
                envent_on_dav.delete()
            else:
                raise ValueError(f"VEVENT {alert.ident} not found on DAV")
        elif alert.dav_type == DAVType.VTODO:
            todo_on_dav = calendar.todo_by_uid(alert.ident)
            if todo_on_dav:
                LOG.debug(f"Removing VTODO ({alert.alert_name}) from DAV")
                todo_on_dav.delete()
            else:
                raise ValueError(f"VTODO {alert.ident} not found on DAV")

    def mark_todo_complete(self, alert: Alert) -> None:
        """
        deletes a specific Todo item and marks it as complete on the DAV service
        :param alert: a Reminder/Todo object to be dropped
        """
        if all([self.dav_active,
                alert.synchronized,
                alert.calendar,
                alert.service]):
            calendar = self.get_dav_calendar(alert.service, alert.calendar)
            _todos = calendar.todos(sort_keys=False)
            for todo in _todos:
                if str(todo.icalendar_instance.subcomponents[0]["UID"]) == alert.ident:
                    todo.complete()

        # if alert.related_to:
        #     related = self.get_alert(alert.related_to)
        #     related.children.remove(alert.ident)

        self.rm_alert(alert.ident)

    def sync_dav(self) -> None:
        """
        Keeps alert and the CalDAVs defined in the skills initialization up to-date.
        The logic would ensure every future event (in a certain timeframe) on DAV gets
        synced. It is possible to change dates on DAV that would also be fetched and
        updated on the local storage without traces.
        """
        if not self.dav_active:
            raise ValueError("DAV is not active")
        calendars = self.get_dav_calendars()
        if not calendars:
            LOG.debug("No DAV calender to sync")
            return

        ids = set()
        with SYNC_LOCK:
            for calendar in calendars:
                LOG.debug(f"CalDAV: Sync alerts from {calendar.name}")
                alerts = get_dav_items(calendar)
                for alert in alerts:
                    # to be on the safe side (potential loop: DAV - local pingpong)
                    if (
                        alert.dav_type == DAVType.VEVENT
                        and alert.expiration is None
                    ):
                        continue
                    ids.add(alert.ident)
                    if alert.ident not in self.pending_ids:
                        self.add_alert(alert)
                        LOG.info(
                            (
                                f"CalDAV: New {DAVType(alert.dav_type).name} received "
                                f"from {calendar.id}/{calendar.name}: {alert.alert_name}"
                            )
                        )
                    # check if the event got edited upstream to replace the alert
                    else:
                        stored_alert = self.get_alert(alert.ident)
                        if stored_alert and properties_changed(stored_alert, alert):
                            self.rm_alert(stored_alert.ident)
                            self.add_alert(alert)
                            # keep the alert type as it is hard to determine reminder/event
                            alert.alert_type = stored_alert.alert_type
                            LOG.info(
                                (
                                    f"CalCAV: Replaced {DAVType(alert.dav_type).name} from "
                                    f"({calendar.id}/{calendar.name}): {alert.alert_name}"
                                )
                            )
                    self.mark_alert_synchron(alert)

            # the other way around
            LOG.debug(f"CalDAV: Sync local alerts")
            alert_to_dav = self.pending_ids.difference(ids, self._synchron_ids)
            for id in alert_to_dav:
                alert = self.get_alert(id)
                ids.add(id)
                if any([
                    alert.alert_type in _SYNC_RESTRICTED,
                    alert.skip_sync,
                    alert.service not in self.dav_services,
                    alert.calendar not in self.dav_calendars
                ]):
                    continue
                calendar = self.get_dav_calendar(alert.service, alert.calendar)
                if alert.dav_type == DAVType.VEVENT:
                    calendar.save_event(alert.to_ical())
                elif alert.dav_type == DAVType.VTODO:
                    calendar.save_todo(alert.to_ical())
                self.mark_alert_synchron(alert)
                LOG.info(
                    (
                        f"CalDAV: {DAVType(alert.dav_type).name} ({alert.alert_name}) "
                        f"synced to {alert.service}/{alert.calendar}"
                    )
                )

            # remove the rest (if not active or missed)
            # NOTE: alerts with repeat info are still pending when in active state
            for id in self.pending_ids.difference(ids):
                if id not in self.missed_ids.union(self.active_ids):
                    self.rm_alert(id)

        self._dump_cache()

    # shutdown
    def shutdown(self):
        """
        Shutdown the Alert Manager. Mark any active alerts as missed and
        update the alerts cache on disk. Pending schedules are left with the
        scheduler, which replays them when it comes back.
        """
        for id in list(self.active_alerts):
            self.mark_alert_missed(id)
        self._dump_cache()
