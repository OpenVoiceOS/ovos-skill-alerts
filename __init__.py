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

import os
import time
from datetime import datetime, timedelta
from threading import RLock
from typing import List, Optional

from dateutil.relativedelta import relativedelta
from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager
from ovos_date_parser import nice_date_time, nice_time, nice_duration
from ovos_number_parser import pronounce_number
from ovos_skill_alerts.util import AlertState, MatchLevel, AlertPriority, WEEKDAYS
from ovos_skill_alerts.util.alert import Alert, AlertType, DAVType, LOCAL_USER
from ovos_skill_alerts.util.alert_manager import AlertManager, SYNC_LOCK
from ovos_skill_alerts.util.config import use_24h_format, get_default_tz, DEFAULT_SETTINGS
from ovos_skill_alerts.util.locale import (
    translate,
    voc_match,
    spoken_duration,
    spoken_alert_type,
    spoken_weekday,
    get_alert_dialog_data,
    get_alert_type_from_intent,
    datetime_display
)
from ovos_skill_alerts.util.media import (
    ocp_query,
    ocp_request,
    get_media_source_from_intent
)
from ovos_skill_alerts.util.parse_utils import (
    tokenize_utterance,
    build_alert_from_intent,
    parse_alert_name_from_message,
    parse_alert_time_from_message,
    parse_timedelta_from_message,
    parse_relative_time_from_message,
    parse_timeframe_from_message,
    parse_alert_name_and_time_from_message,
    parse_end_condition_from_message,
    parse_alert_priority_from_message,
    parse_audio_file_from_message,
    parse_repeat_from_message,
    get_week_range,
    validate_dt_or_delta,
    validate_number,
    fuzzy_match,
    fuzzy_match_alerts
)
from ovos_skill_alerts.util.ui_models import build_gui_data
from ovos_utils import create_daemon, classproperty
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils.sound import play_audio
from ovos_utterance_normalizer import UtteranceNormalizerPlugin
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.converse import ConversationalSkill
from ovos_workshop.skills.ovos import join_word_list


class AlertSkill(ConversationalSkill):
    def __init__(self, *args, **kwargs):
        # kwarg only used for unittests
        if "alerts_path" in kwargs:
            self.alerts_path = kwargs.pop("alerts_path")
        else:
            self.alerts_path = None

        self._alert_manager = None
        self._gui_timer_lock = RLock()

        super().__init__(*args, **kwargs)

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=False,
                                   network_before_load=False,
                                   gui_before_load=False,
                                   requires_internet=False,
                                   requires_network=False,
                                   requires_gui=False,
                                   no_internet_fallback=True,
                                   no_network_fallback=True,
                                   no_gui_fallback=True)

    @property
    def alert_manager(self) -> AlertManager:
        """
        Get the AlertManager that tracks all Alert objects and their statuses.
        """
        if not self._alert_manager:
            raise RuntimeError("Requested AlertManager before initialize")
        return self._alert_manager

    @property
    def speak_alarm(self) -> bool:
        """
        If true, speak dialog for expired alarms instead of playing audio files.
        """
        return self.settings.get('speak_alarm', False)

    @property
    def speak_timer(self) -> bool:
        """
        If true, speak dialog for expired alarms instead of playing audio files.
        """
        return self.settings.get('speak_timer', True)

    @property
    def alarm_sound_file(self) -> str:
        """
        Return the path to a valid alarm sound resource file
        """
        filename = self.settings.get('sound_alarm') or 'default-alarm.wav'
        if os.path.isfile(filename):
            return filename
        file = self.find_resource(filename)
        if not file:
            LOG.warning(f'Could not resolve requested file: {filename}')
            file = os.path.join(os.path.dirname(__file__), 'res', 'snd',
                                'default-alarm.wav')
        if not file:
            raise FileNotFoundError(f"Could not resolve sound: {filename}")
        return file

    @property
    def timer_sound_file(self) -> str:
        """
        Return the path to a valid timer sound resource file
        """
        filename = self.settings.get('sound_timer') or 'default-timer.wav'
        if os.path.isfile(filename):
            return filename
        file = self.find_resource(filename)
        if not file:
            LOG.warning(f'Could not resolve requested file: {filename}')
            file = os.path.join(os.path.dirname(__file__), 'res', 'snd',
                                'default-timer.wav')
        if not file:
            raise FileNotFoundError(f"Could not resolve sound: {filename}")
        return file

    @property
    def play_volume(self) -> int:
        """
        Return the volume to play audio files at
        """
        LOG.debug(f"play_volume: {int(self.settings.get('play_volume', 100))}")
        return int(self.settings.get('play_volume', 100)) / 100

    @property
    def snooze_duration(self) -> timedelta:
        """
        Get default snooze duration
        """
        snooze_minutes = self.settings.get('snooze_mins') or 15
        if not isinstance(snooze_minutes, int):
            LOG.error(f'Invalid `snooze_minutes` in settings. '
                      f'Expected int but got: {snooze_minutes}')
            snooze_minutes = 15
        return timedelta(minutes=snooze_minutes)

    @property
    def alert_timeout_seconds(self) -> int:
        """
        Return the number of seconds to repeat an alert before marking it missed
        """
        timeout_minutes = self.settings.get('timeout_min') or 1
        if not isinstance(timeout_minutes, (int, float,)):
            LOG.error(f'Invalid `timeout_min` in settings. '
                      f'Expected int/float but got: {type(timeout_minutes)}')
            timeout_minutes = 1
        return 60 * timeout_minutes

    @property
    def use_24hour(self) -> bool:
        return use_24h_format()

    def initialize(self):
        # merge default settings
        for k, v in DEFAULT_SETTINGS.items():
            if k not in self.settings:
                self.settings[k] = v

        # Initialize manager with any cached alerts
        self._alert_manager = AlertManager(
            self.alerts_path or self.file_system.path,
            self.event_scheduler,
            (
                self._alert_prenotification,
                self._alert_expired,
            ),
        )

        self.dav_services = list()
        self.sync_frequency: int = 0

        # settings callback
        self.settings_change_callback = self._init_dav_clients

        # Update Homescreen UI models
        # this is (falsely) assuming gui connected == skill homescreen
        if self.gui.connected:
            self.add_event("ovos.homescreen.displayed", self.on_ready, once=True)  # homescreen >0.0.3a6
        else:
            self.add_event("mycroft.ready", self.on_ready, once=True)

        self.add_event("ovos.alerts.get_alerts", self._event_get_alerts)
        self.add_event("ovos.alerts.dismiss_notification",
                       self._gui_dismiss_notification)
        self.add_event("ovos.gui.show.active.timers", self._on_display_gui)
        self.add_event("ovos.gui.show.active.alarms", self._on_display_gui)

        self.gui.register_handler("ovos.alerts.cancel_timer",
                                  self._gui_cancel_timer)
        self.gui.register_handler("ovos.alerts.cancel_alarm",
                                  self._event_cancel_alarm)
        self.add_event("ovos.alerts.cancel_alarm",
                       self._event_cancel_alarm)
        self.gui.register_handler("ovos.alerts.snooze_alarm",
                                  self._event_snooze_alarm)
        self.add_event("ovos.alerts.snooze_alarm",
                       self._event_snooze_alarm)

    def on_ready(self, _: Message):
        """
        On ready, update the Home screen elements
        """
        # wait until gui is ready to receive update_homescreen messages
        time.sleep(2)
        self._update_homescreen()
        self._init_dav_clients()

    def _init_dav_clients(self):
        # Initialize DAV clients and voice errors regarding DAV
        with SYNC_LOCK:
            dav_services = self.settings.get("services", "").split(",")
            sync_frequency = int(self.settings.get("frequency", 15))
            if dav_services != self.dav_services or \
                    sync_frequency != self.sync_frequency:
                if dav_services[0]:
                    LOG.debug(f"Init DAV Client for {','.join(dav_services)}")
                errors = self._alert_manager.init_dav_clients(dav_services,
                                                              sync_frequency)
                for dialog, services in errors.items():
                    if services:
                        self.speak_dialog(dialog,
                                          {"services": join_word_list(services,
                                                                      connector="and",
                                                                      sep=",",
                                                                      lang=self.lang)})
                self.dav_services = dav_services
                self.sync_frequency = sync_frequency

    # Intent Handlers
    #@killable_intent()
    @intent_handler(IntentBuilder("CreateAlarm").require("alarm")
                    .require("create").optionally("question")
                    .optionally("playable").optionally("weekdays")
                    .optionally("weekends").optionally("everyday")
                    .optionally("repeat").optionally("until")
                    .optionally("priority"))
    def handle_create_alarm(self, message: Message):
        """
        Intent handler for creating an alarm
        :param message: Message associated with request
        """
        alarm = build_alert_from_intent(message)
        if alarm.expiration is None:
            time_ = self.get_response(
                "alarm_ask_time", validator=validate_dt_or_delta, num_retries=0
            )
            if isinstance(time_, datetime):
                alarm.expiration = time_
            elif isinstance(time_, timedelta):
                alarm.expiration = alarm.created + time_
            else:
                self.speak_dialog("error_no_time", {"kind": "alarm"}, wait=True)
                return

        self.confirm_alert(alarm, message)

    @intent_handler(IntentBuilder("CreateAlarmAlt").require("wake")
                    .optionally("question").optionally("playable")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("repeat")
                    .optionally("until").optionally("priority"))
    def handle_create_alarm_alt(self, message: Message):
        """
        Alternate intent handler for creating an alarm
        :param message: Message associated with request
        """
        return self.handle_create_alarm(message)

    @intent_handler(IntentBuilder("CreateOcpAlarm").require("alarm")
                    .require("media").require("create").optionally("question"))
    def handle_ocp_alarm(self, message: Message):
        if not self.bus.wait_for_response(Message("ovos.common_play.ping"),
                                          "ovos.common_play.pong"):
            return self.speak_dialog("ocp_missing")

        ocp_result = self._ocp_query(message)
        if ocp_result is None:
            return self.speak_dialog("ocp_breaking_up")

        alert_time = parse_alert_time_from_message(message)
        # in case no time was specified, use the next upcoming alarm
        if not alert_time:
            alarms = self._get_alerts_list(AlertType.ALARM)
            if not alarms:
                return self.speak_dialog("list_alert_none_upcoming",
                                         {"kind": spoken_alert_type(AlertType.ALARM, self.lang)})
            alarms[0].ocp_request = ocp_result
        else:
            alarm = build_alert_from_intent(message)
            alarm.ocp_request = ocp_result
            assert alarm.media_type == "ocp"
            self.confirm_alert(alarm, message)

    @intent_handler(IntentBuilder("CreateOcpAlarmAlt").require("wake")
                    .require("media").optionally("question"))
    def handle_ocp_alarm_alt(self, message: Message):
        return self.handle_ocp_alarm(message)

    #@killable_intent()
    @intent_handler(IntentBuilder("CreateTimer").require("create")
                    .require("timer").optionally("question")
                    .optionally("until"))
    def handle_create_timer(self, message: Message):
        """
        Intent handler for creating a timer
        :param message: Message associated with request
        """
        alert = build_alert_from_intent(message)
        # stopwatch mode (without time specified - counts from now)
        # gets no expiration notification treatment
        if alert.stopwatch_mode:
            self.alert_manager._active_alerts[alert.ident] = alert
            self.speak_dialog('confirm_timer_started', {"remaining": ""})
            self._display_alert(alert)
            self._activate()
            return

        self.confirm_alert(alert, message)

    #@killable_intent()
    @intent_handler(IntentBuilder("CreateReminder").require("create")
                    .require("reminder").optionally("question")
                    .optionally("playable").optionally("weekdays")
                    .optionally("weekends").optionally("everyday")
                    .optionally("repeat").optionally("until")
                    .optionally("priority"))
    def handle_create_reminder(self, message: Message):
        """
        Intent handler for creating a reminder
        :param message: Message associated with request
        """
        alert = build_alert_from_intent(message)
        alert_type, spoken_type = get_alert_type_from_intent(message)

        # if alert.alert_name is None:
        #     return

        if alert.expiration is None:
            time_ = self.get_response(
                "reminder_ask_time", validator=validate_dt_or_delta, num_retries=0
            )
            #if response and response != "no":
            if isinstance(time_, datetime):
                alert.expiration = time_
            elif isinstance(time_, timedelta):
                alert.expiration = alert.created + time_
            # will be handled as todo entry
            else:
                alert.alert_type = AlertType.TODO
                alert.dav_type = DAVType.VTODO
                return self.handle_create_todo(message, alert)

        # check for overlapping reminder
        overlapping = \
            self.alert_manager.get_alerts_in_timeframe(alert.expiration,
                                                       alert.until,
                                                       alert_type)

        if overlapping:
            dialog_data = {"event": join_word_list([r.alert_name for r in overlapping],
                                                   connector="and", sep=",", lang=self.lang)}
            end = [a.until for a in overlapping if a.until]
            if end:
                dialog_data["begin"] = nice_time(min([a.expiration for a in overlapping]), lang=self.lang)
                dialog_data["end"] = nice_time(max(end), lang=self.lang)
                dialog = "alert_overlapping_duration_ask"
            else:
                dialog_data["begin"] = join_word_list([nice_time(a.expiration, lang=self.lang) for a in overlapping],
                                                      connector="and", sep=",", lang=self.lang)
                dialog = "alert_overlapping_ask"

            if self.ask_yesno(dialog, dialog_data) in ("no", None):
                return

        if alert.alert_type == AlertType.EVENT:
            self.ask_for_prenotification(alert)
        if self.alert_manager.dav_active:
            self.specify_dav_attributes(alert, spoken_type)
        self.confirm_alert(alert, message)

    #@killable_intent()
    @intent_handler(IntentBuilder("CreateReminderAlt").require("remind")
                    .optionally("question").optionally("playable")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("repeat")
                    .optionally("until"))
    def handle_create_reminder_alt(self, message: Message):
        """
        Alternate intent handler for creating a reminder
        :param message: Message associated with request
        """
        self.handle_create_reminder(message)

    #@killable_intent()
    @intent_handler(IntentBuilder("CreateEvent")
                    .require("create").require("event")
                    .optionally("question").optionally("playable")
                    .optionally("everyday").optionally("weekdays")
                    .optionally("weekends").optionally("repeat")
                    .optionally("until").optionally("priority")
                    .optionally("remind").optionally("all_day"))
    def handle_create_event(self, message: Message):
        """
        Intent handler for creating an event. Wraps handle_create_reminder
        :param message: Message associated with request
        """
        LOG.debug("Create Event calling Reminder")
        self.handle_create_reminder(message)

    @intent_handler(IntentBuilder("RescheduleAlert")
                    .require("change").optionally("next")
                    .one_of("alarm", "reminder", "event", "timer")
                    .optionally("question").optionally("earlier")
                    .optionally("all_day"))
    def handle_reschedule_alert(self, message: Message):
        """
        Intent to reschedule an alarm, reminder, event or timer
        :param message: Message associated with request
        """
        alert_type, spoken_type = get_alert_type_from_intent(message)
        alert = self._resolve_requested_alert(message, alert_type)

        if alert is None:
            return self.speak_dialog("error_no_scheduled_kind",
                                     {"kind": spoken_type}, wait=True)

        # ref_day = convenience experimental because of repeating alerts
        # user only have to state the time instead remembering the day
        ref_day = alert.expiration.replace(hour=0, minute=0, second=0)
        anchor_time = ref_day if alert.has_repeat else None

        if message.data.get("all_day"):
            # the appropriate time is set by the object
            alert.is_all_day = True
            rescheduled_time = alert.expiration.date()
            dialog = "alert_rescheduled_all_day"
        else:
            alert.is_all_day = False
            rescheduled_time = parse_relative_time_from_message(message, anchor_time=anchor_time)
            dialog = "alert_rescheduled"

        if rescheduled_time is None:
            return self.speak_dialog("error_no_time", {"kind": spoken_type}, wait=True)

        once = True
        if alert.has_repeat and \
                self.ask_yesno("reschedule_recurring_ask",
                               {"type": spoken_type}) == "yes":
            once = False

        rescheduled = self.alert_manager.reschedule_alert(alert, rescheduled_time, once)
        self._display_alert(rescheduled)
        dialog_data = get_alert_dialog_data(rescheduled, self.lang)
        self.speak_dialog(dialog, dialog_data, wait=True)
        # ask if prenotification should be adjusted
        if rescheduled.prenotification:
            self.ask_for_prenotification(rescheduled,
                                         "alert_rescheduled_prenotification",
                                         dialog_data)

    @intent_handler(IntentBuilder("RescheduleAlertAlt")
                    .one_of("earlier", "later").optionally("next")
                    .one_of("alarm", "reminder", "event", "timer")
                    .optionally("question"))
    def handle_reschedule_alert_alt(self, message: Message):
        LOG.debug("alt schedule")
        return self.handle_reschedule_alert(message)

    @intent_handler(IntentBuilder("ChangeProperties")
                    .require("change").optionally("next")
                    .one_of("alarm", "reminder", "event", "timer")
                    .one_of("until", "repeat", "priority")
                    .optionally("weekdays").optionally("weekends")
                    .optionally("everyday").optionally("question"))
    def handle_change_properties(self, message: Message):
        """
        Intent to reschedule an alarm, reminder, event or timer
        :param message: Message associated with request
        """
        alert_type, spoken_type = get_alert_type_from_intent(message)
        alert: Alert = self._resolve_requested_alert(message, alert_type)

        if alert is None:
            return self.speak_dialog("error_no_scheduled_kind",
                                     {"kind": spoken_type}, wait=True)

        if message.data.get("priority"):
            old_priority = alert.priority
            priority = parse_alert_priority_from_message(message)
            if old_priority != priority:
                alert.priority = priority
                self.speak_dialog("property_changed_priority",
                                  {"num": priority})
            else:
                return self.speak_dialog("error_same_priority")
        elif message.data.get("until"):
            end = parse_end_condition_from_message(message)
            if end:
                alert.until = end
                dialog_data = get_alert_dialog_data(alert, self.lang)
                self.speak_dialog("alert_rescheduled_end", dialog_data)
            else:
                return self.speak_dialog("error_no_time", {"kind": spoken_type})
        elif message.data.get("repeat"):
            repeat = parse_repeat_from_message(message)
            if repeat:
                if self.alert_manager.reschedule_repeat(alert, repeat):
                    dialog_data = get_alert_dialog_data(alert, self.lang)
                    self.speak_dialog("alert_rescheduled_repeat", dialog_data)
                else:
                    pass
            else:
                self.speak_dialog("error_no_repeat", {"kind": spoken_type})
        else:
            return

        self._display_alert(alert)
        self.alert_manager.sync_dav_item(alert)

    @intent_handler(IntentBuilder("ChangeMediaProperties")
                    .require("change").optionally("next")
                    .one_of("alarm", "reminder", "event", "timer")
                    .require("playable"))
    def handle_change_media_properties(self, message: Message):

        alert_type, spoken_type = get_alert_type_from_intent(message)
        alert: Alert = self._resolve_requested_alert(message, alert_type)

        old_media = alert.media_type
        new_media = get_media_source_from_intent(message)
        if new_media == "file":
            audio = parse_audio_file_from_message(message)
            if audio:
                alert.audio_file = f"file:/{audio}"
            else:
                return self.speak_dialog("error_no_script", {"kind": spoken_type})

        if old_media:
            self.speak_dialog("media_type_changed",
                              {"old": translate(old_media, lang=self.lang),
                               "new": translate(new_media, lang=self.lang)})
        else:
            self.speak_dialog("media_type_set",
                              {"new": translate(new_media, lang=self.lang)})

    # Query Alerts
    @intent_handler(IntentBuilder("ListAlerts").require("query")
                    .one_of("alarm", "reminder", "event", "alert", "remind")
                    .optionally("and").optionally("stored"))
    def handle_event_timeframe_check(self, message: Message):
        """
        Intent to check if there are events stored at a given datetime /
        within a given timeframe. If no datetime is passed list all of given type
        Examples:
            Are there any events pending between monday 10:00 am and 12:00 am
            Are there any events stored on tuesday
            Are there any events at 8 pm
        :param message: Message associated with request
        """
        normalizer = UtteranceNormalizerPlugin.get_normalizer(lang=self.lang)
        utterance = normalizer.normalize(message.data.get("utterance", "")).lower()
        alert_type, spoken_type = get_alert_type_from_intent(message)
        begin, end = parse_timeframe_from_message(message)

        # week range
        if self.voc_match("week", utterance, lang=self.lang):
            now = datetime.now(get_default_tz())
            # hack bc LF return None on "this week"
            begin, end = get_week_range(begin or now)
        elif not begin and not end:
            if self.voc_match("next", utterance, lang=self.lang):
                return self.handle_next_alert(message)
            return self.handle_list_all_alerts(message)

        overlapping = self.alert_manager.get_alerts_in_timeframe(begin,
                                                                 end,
                                                                 alert_type)
        if overlapping:
            self._display_alerts(alert_type, overlapping)
            self.speak_dialog("list_alert_timeframe_intro",
                              {"num": len(overlapping),
                               "type": spoken_type})
            for alert in overlapping:
                data = get_alert_dialog_data(alert, self.lang, begin)
                if "end" in data and not alert.is_all_day:
                    self.speak_dialog("list_alert_w_duration", data)
                else:
                    self.speak_dialog("list_alert_wo_duration", data)
        else:
            self.speak_dialog("list_alert_timeframe_none")

    def handle_list_all_alerts(self, message: Message):
        """
        Handler to handle request for all alerts (kind optional)
        :param message: Message associated with request
        """
        alert_type, spoken_type = get_alert_type_from_intent(message)
        alerts_list = self._get_alerts_list(alert_type,
                                            disposition=AlertState.PENDING)
        if not alerts_list:
            self.speak_dialog("list_alert_none_upcoming",
                              {"kind": spoken_type}, wait=True)
            return

        self._display_alerts(alert_type, alerts_list)

        if message.data.get("alert"):
            kinds = {(a.alert_type.value, spoken_alert_type(a.alert_type))
                     for a in alerts_list if a.expiration is not None}
        else:
            kinds = {(alert_type.value, spoken_type)}

        # Restrict to max 10(?) alerts
        if len(alerts_list) > 10:
            alerts_list = alerts_list[:10]

        for id, kind in kinds:
            self.speak_dialog("list_alert_intro", {"kind": kind},
                              wait=True)
            for alert in alerts_list:
                if alert.alert_type.value != id:
                    continue

                data = get_alert_dialog_data(alert, self.lang)
                dialog = ""
                if data["name"]:
                    dialog = f"{data['name']} -"
                if "repeat" in data:
                    dialog = f"{dialog} {self.resources.render_dialog('repeating_every', data)}"
                if alert_type == AlertType.TIMER:
                    dialog = f"{dialog} {self.resources.render_dialog('in_time', data)}\n"
                else:
                    dialog = f"{dialog} {self.resources.render_dialog('at_time', data)}\n"

                self.speak(dialog, wait=True)
            # short break in between different alert types
            time.sleep(1)

    def handle_next_alert(self, message: Message):
        """
        Intent handler to handle request for the next alert (kind optional)
        :param message: Message associated with request
        """
        alert_type, spoken_type = get_alert_type_from_intent(message)
        alerts_list = self._get_alerts_list(alert_type,
                                            disposition=AlertState.PENDING)
        if not alerts_list:
            return self.speak_dialog("list_alert_none_upcoming",
                                     {"kind": spoken_type},
                                     wait=True)

        alert = alerts_list[0]  # sorted time ascending
        data = get_alert_dialog_data(alert, self.lang)

        self._display_alert(alert)

        if alert.alert_type == AlertType.TIMER:
            dialog = "next_alert_timer"
        else:
            dialog = "next_alert"

        self.speak_dialog(dialog, data, wait=True)

    @intent_handler(IntentBuilder("TimerStatus").one_of("time", "timer").require("remaining").optionally("query"))
    def handle_timer_status(self, message: Message):
        """
        Intent handler to handle request for timer status (name optional)
        :param message: Message associated with request
        """
        name = parse_alert_name_from_message(message)

        user_timers = self._get_alerts_list(AlertType.TIMER, name=name)
        if not user_timers:
            return self.speak_dialog("timer_status_none_active", wait=True)

        # show timers if not already up
        self._display_alerts(AlertType.TIMER, user_timers)

        for i, timer in enumerate(user_timers):
            dialog_data = get_alert_dialog_data(timer, self.lang)
            if not dialog_data["name"] and len(user_timers) > 1:
                dialog_data["name"] = pronounce_number(i + 1, ordinals=True)
            self.speak_dialog("timer_status", dialog_data, wait=True)

    # TODO - connect this to naptime skill - mycroft.awoken bus message
    @intent_handler("missed_alerts.intent")
    def handle_missed_alerts(self, _: Message):
        """
        Intent to handle any alerts that have been missed.
        :param message: Message associated with request
        """
        missed_alerts = self._get_alerts_list(AlertType.ALL,
                                              disposition=AlertState.MISSED)
        if missed_alerts:  # TODO: Unit test this DM
            self.speak_dialog("list_alert_missed_intro", wait=True)
            for alert in missed_alerts:
                data = get_alert_dialog_data(alert, self.lang)
                self.speak_dialog("list_alert_missed", data, wait=True)
                self._dismiss_alert(alert.ident, speak=False)
        else:
            self.speak_dialog("list_alert_none_missed", wait=True)

    @intent_handler(IntentBuilder("CancelAlert").require("cancel")
                    .optionally("stored").optionally("next").optionally("and")
                    .one_of("alarm", "timer", "reminder", "event", "alert"))
    def handle_cancel_alert(self, message: Message):
        """
        Intent handler to handle request to cancel alerts
        :param message: Message associated with request
        """
        alert_type, spoken_type = get_alert_type_from_intent(message)
        begin, end = parse_timeframe_from_message(message)
        if begin and end:
            alerts = self.alert_manager.get_alerts_in_timeframe(begin,
                                                                end,
                                                                alert_type)
        else:
            alerts = self._get_alerts_list(alert_type,
                                           disposition=AlertState.PENDING)
        # Notify nothing to cancel
        if not alerts:
            if alert_type in (AlertType.ALL, AlertType.UNKNOWN):
                self.speak_dialog("error_nothing_to_cancel", wait=True)
            else:
                self.speak_dialog("error_no_scheduled_kind",
                                  {"kind": spoken_type}, wait=True)
            return

        # Cancel all alerts of some specified type
        if message.data.get("stored") or (begin and end):
            # TODO add saveguard for DAV conten?
            for alert in alerts:
                self._dismiss_alert(alert.ident, drop_dav=True)
            return self.speak_dialog("confirm_cancel_timeframe" if begin else "confirm_cancel_all",
                                     {"kind": spoken_type, "num": len(alerts)},
                                     wait=True)
        # Only one candidate alert
        elif len(alerts) == 1 or message.data.get("next"):
            alert = alerts[0]
        # Resolve the requested alert
        else:
            alert = self._resolve_requested_alert(message, alert_type)

            if alert is None:
                self.speak_dialog("error_nothing_to_cancel", wait=True)
                return

        # if default name, replace alert_type substring
        name = alert.alert_name.replace(spoken_type, "").strip()

        self._dismiss_alert(alert.ident, drop_dav=True)
        self.speak_dialog('confirm_cancel_alert',
                          {'kind': spoken_type,
                           'name': name}, wait=True)

    # Todo Lists
    #@killable_intent()
    @intent_handler(IntentBuilder("CreateList").require("create").require("list"))
    def handle_create_todo(self, message: Message, alert: Optional[Alert] = None):
        """
        Intent to create a todo list
        :param message: Message associated with request
        """
        if alert:
            name = alert.alert_name
        else:
            name = parse_alert_name_from_message(message)

        todo_lists = self._get_alerts_list(AlertType.TODO, name=name)
        if todo_lists:
            self.speak_dialog(
                "list_todo_already_exist", {"name": name}, wait=True
            )
            return
        if not alert:
            alert = Alert.create(
                alert_name=name, alert_type=AlertType.TODO, dav_type=DAVType.VTODO, lang=self.lang
            )
        if self.alert_manager.dav_active:
            self.specify_dav_attributes(alert,
                                        spoken_alert_type(AlertType.TODO, self.lang))
        self.alert_manager.add_alert(alert)
        # NOTE: the alert might be a redirected reminder
        if "list" in message.data:
            return self.handle_add_subitem_to_todo(message)

        self.speak_dialog("confirm_todo_set", wait=True)

    #@killable_intent()
    @intent_handler(
        IntentBuilder("AddListSubitems")
        .require("create").require("list").require("items")
    )
    def handle_add_subitem_to_todo(self, message: Message):
        """
        Intent to add a/multiple subitems to an existing todo list (eg shopping)
        :param message: Message associated with request
        """
        name = parse_alert_name_from_message(message)

        todo = self._resolve_requested_alert(message, AlertType.TODO)
        if todo is None:
            return self.speak_dialog("list_todo_dont_exist", {"name": name})

        # I guess the best bet is to voice out/show the existing entries to avoid duplicates
        if len(todo.children) > 0:
            self.handle_todo_list_entries(alert=todo)

        # get_response in rapid sucession
        items = self._get_response_cascade(
            "list_todo_add_ask",
            data={"name": todo.alert_name, "lang": self.lang},
            message=message
        )
        for item in items:
            alert = Alert.create(
                alert_name=item,
                alert_type=AlertType.TODO,
                dav_calendar=todo.calendar,
                dav_service=todo.service,
                context=dict(related_to=todo.ident),
                lang=self.lang
            )
            self.alert_manager.add_alert(alert)
        self.speak_dialog(
            "list_todo_subitems_added",
            {"num": pronounce_number(len(items))},
        )

    @intent_handler(
        IntentBuilder("QueryListNames")
        .require("query").require("list").optionally("stored")
    )
    def handle_query_todo_list_names(self, message: Message):
        """
        Intent to get a list of todos (todos WITH subitems)
        :param message: Message associated with request
        """
        # only lists
        todos = self.alert_manager.get_connected_alerts(type=AlertType.TODO)
        names = [todo.alert_name for todo in todos]
        LOG.debug(names)
        if todos:
            if self.gui.connected:
                self._display_list(todos)
            self.speak_dialog(
                "list_todo_lists",
                {"num": pronounce_number(len(names)),
                 "lists": join_word_list(names, connector="and", sep=",", lang=self.lang)},
            )
        else:
            self.speak_dialog("list_todo_no_lists")

    @intent_handler(
        IntentBuilder("QueryTodoEntries")
        .require("query").require("todo").optionally("items")
        .optionally("stored")
    )
    def handle_query_todo_reminder_names(self, message: Message):
        """
        Intent to get a list of todos (todos WITHOUT subitems)
        :param message: Message associated with request
        """
        # only todos without children (and parents)
        todos = self.alert_manager.get_unconnected_alerts(type=AlertType.TODO)
        if todos:
            if self.gui.connected:
                self._display_list(todos)
            self.speak_dialog(
                "list_todo_reminder",
                {"reminders": join_word_list([todo.alert_name for todo in todos],
                                             connector="and", sep=",", lang=self.lang)},
            )
        else:
            self.speak_dialog("list_todo_no_reminder")

    @intent_handler(
        IntentBuilder("QueryListEntries")
        .require("query").require("list").require("items")
    )
    def handle_todo_list_entries(self, message: Optional[Message] = None, alert: Optional[Alert] = None):
        """
        Intent to get the items from a specific todo list
        :param message: Message associated with request
        """
        if message:
            name = parse_alert_name_from_message(message)
            alert = self._resolve_requested_alert(message, AlertType.TODO)
        if alert is None:
            return self.speak_dialog("list_todo_dont_exist", {"name": name})

        list_entries = self.alert_manager.get_children(alert.ident)
        if list_entries:
            self.speak_dialog(
                "list_todo_subitems",
                {"name": alert.alert_name,
                 "items": join_word_list([alert.alert_name for alert in list_entries],
                                         connector="and", sep=",", lang=self.lang)},
                wait=True,
            )
        else:
            self.speak_dialog("list_todo_no_subitems")

        if list_entries and self.gui.connected:
            self._display_list(list_entries, alert.alert_name)
            # delay if this handler is used in context
            time.sleep(2)

    #@killable_intent()
    @intent_handler(
        IntentBuilder("DeleteListEntries")
        .require("delete").require("items").require("list").optionally("stored")
    )
    def handle_delete_todo_list_entries(self, message: Message):
        """
        Intent to delete one or more todo items
        :param message: Message associated with request
        """
        todo = self._resolve_requested_alert(message,
                                             AlertType.TODO,
                                             dialog="list_item_delete_selection_intro")

        if todo is None:
            return

        if message.data.get("stored"):
            to_delete = [todo.alert_name for todo in
                         self.alert_manager.get_children(todo.ident)]
        else:
            # show/voice entries     
            self.handle_todo_list_entries(alert=todo)

            to_delete = self._get_response_cascade("remove_list_items_ask",
                                                   {"lang": self.lang},
                                                   message=message)
        deleted = to_delete[:]
        for item in to_delete:
            entries = self._get_alerts_list(AlertType.TODO, name=item)
            # ensure no entries from another list
            entries = list(
                filter(lambda alert: alert.related_to == todo.ident, entries)
            )
            entry = self._pick_one_by_name(entries, "pick_multiple_entries")
            if entry:
                self.alert_manager.mark_todo_complete(entry)
            else:
                self.speak_dialog("list_todo_dont_exist", {"name": item})
                deleted.remove(item)
        self.speak_dialog("list_todo_num_deleted",
                          {"num": pronounce_number(len(deleted))})

    #@killable_intent()
    @intent_handler(
        IntentBuilder("DeleteList")
        .require("delete").require("list")
    )
    def handle_delete_todo_list(self, message: Message):
        todo = self._resolve_requested_alert(message,
                                             AlertType.TODO)

        if todo is None:
            return

        children = self.alert_manager.get_children(todo.ident)
        for child in children:
            self.alert_manager.mark_todo_complete(child)
        self.alert_manager.mark_todo_complete(todo)
        self.speak_dialog("list_deleted", {"name": todo.alert_name})

    #@killable_intent()
    @intent_handler(
        IntentBuilder("DeleteTodoEntries")
        .require("delete").require("todo").optionally("items").optionally("stored")
    )
    def handle_delete_todo_entries(self, message: Message):

        name = parse_alert_name_from_message(message)
        todos = self.alert_manager.get_unconnected_alerts(type=AlertType.TODO)

        if not todos:
            return self.speak_dialog("list_todo_no_reminder")

        if message.data.get("stored"):
            to_delete = [todo.alert_name for todo in todos]
        elif name:
            to_delete = [name]
        else:
            self._display_alerts(AlertType.TODO, todos)
            self.speak_dialog(
                "list_todo_subitems",
                {"items": join_word_list([todo.alert_name for todo in todos],
                                         connector="and", sep=",", lang=self.lang)},
                wait=True,
            )
            time.sleep(2)
            to_delete = self._get_response_cascade("remove_list_items_ask",
                                                   {"lang": self.lang},
                                                   message=message)

        deleted = to_delete[:]
        for item in to_delete:
            todo = fuzzy_match_alerts(todos, item, 90)
            if todo:
                self.alert_manager.mark_todo_complete(todo)
            else:
                self.speak_dialog("list_todo_dont_exist", {"name": item})
                deleted.remove(item)
        self.speak_dialog("list_todo_num_deleted",
                          {"num": pronounce_number(len(deleted), lang=self.lang)})

    # Query DAV
    @intent_handler(
        IntentBuilder("CalendarList")
        .require("query")
        .require("calendar")
        .require("choice")
    )
    def handle_speak_calendar_list(self, message: Message):
        """
        Intent to get a list of DAV calendars accessable
        :param message: Message associated with request
        """
        if not self.alert_manager.dav_active:
            self.speak_dialog("dav_inactive")
            return

        calendars = self.alert_manager.get_calendar_names()
        for service, calendars in calendars.items():
            self.speak_dialog(
                "dav_calendar_list",
                data={"service": service, "calendars": join_word_list(calendars,
                                                                      connector="and", sep=",", lang=self.lang)},
            )

    @intent_handler(
        IntentBuilder("DAVSync")
        .require("synchronize").one_of("calendar", "event", "reminder")
    )
    def handle_dav_sync(self, message: Message):
        """
        Handler to synchronize with DAV services on demand
        """
        if not self.alert_manager.dav_active:
            self.speak_dialog("dav_inactive")
            return

        self.alert_manager.sync_dav()

    def confirm_alert(self, alert: Alert, message: Message,
                      anchor_time: Optional[datetime] = None):
        """
        Confirm alert details; get time and name for alerts if not
        specified and schedule.
        :param alert: Alert object built from user request
        :param message: Message associated with request
        :param anchor_time:
        """
        # NOTE: untimed reminder (todo) are added directly without this confirmation
        if alert.expiration is None:
            return self.speak_dialog("alert_expiration_past")

        # Get spoken time parameters
        duration = spoken_duration(alert.expiration,
                                   anchor_time or alert.created,
                                   self.lang)
        # This is patching LF type annotation bug
        # noinspection PyTypeChecker
        spoken_alert_time = \
            nice_time(alert.expiration, lang=self.lang,
                      use_24hour=self.use_24hour, use_ampm=not self.use_24hour)

        # Schedule alert expirations
        self.alert_manager.add_alert(alert)

        # update widget and display alert
        self._update_homescreen(alert)
        self._display_alert(alert)

        if alert.alert_type == AlertType.TIMER:
            self.speak_dialog('confirm_timer_started',
                              {'remaining': duration}, wait=True)
            return

        # Notify one-time Alert
        if not alert.repeat_days and not alert.repeat_frequency:
            if alert.audio_file:
                self.speak_dialog("confirm_alert_playback",
                                  {'name': alert.alert_name,
                                   'begin': spoken_alert_time,
                                   'remaining': duration},
                                  wait=True)
            else:
                spoken_kind = spoken_alert_type(alert.alert_type, self.lang)
                self.speak_dialog('confirm_alert_set',
                                  {'kind': spoken_kind,
                                   'begin': spoken_alert_time,
                                   'remaining': duration}, wait=True)
            return

        # Get spoken repeat interval
        if alert.repeat_frequency:
            repeat_interval = spoken_duration(
                alert.expiration + alert.repeat_frequency,
                alert.expiration,
                self.lang)
        elif len(alert.repeat_days) == 7:
            repeat_interval = translate("day", lang=self.lang)
        elif alert.repeat_days == WEEKDAYS:
            repeat_interval = translate("weekday", lang=self.lang)
        else:
            repeat_interval = join_word_list([spoken_weekday(day, self.lang)
                                              for day in alert.repeat_days],
                                             connector="and", sep=",", lang=self.lang)

        # Notify repeating alert
        if alert.audio_file:
            self.speak_dialog('confirm_alert_recurring_playback',
                              {'name': alert.alert_name,
                               'begin': spoken_alert_time,
                               'repeat': repeat_interval},
                              wait=True)
        else:
            spoken_kind = spoken_alert_type(alert.alert_type, self.lang)
            self.speak_dialog('confirm_alert_recurring',
                              {'kind': spoken_kind,
                               'begin': spoken_alert_time,
                               'repeat': repeat_interval},
                              wait=True)

    def ask_for_prenotification(self, alert: Alert,
                                dialog: str = "alert_prenotification_ask",
                                data: Optional[dict] = None) -> None:
        """
        Asks if a prenotification (short pre notice) should be added
        :param alert: Alert object built from user request
        """
        data = data or dict()
        response = self.get_response(
            dialog,
            data,
            validator=validate_dt_or_delta,
            on_fail="error_no_duration",
            num_retries=1,
        )
        if isinstance(response, (timedelta, datetime, relativedelta)):
            # assumption: The notification will be setup no more than 24 hours before the expiration
            _ref_time = response
            if isinstance(response, datetime):
                _ref_time = datetime.combine(alert.expiration.date(),
                                             response.time())
                if _ref_time > alert.expiration:
                    _ref_time -= timedelta(days=1)
            alert.prenotification = _ref_time

    def specify_dav_attributes(self, alert: Alert, spoken_type: str) -> None:
        """
        Asks whether or not and (if necessary) to which of the available DAV
        services and calendars the alert should be synced to
        :param alert: Alert object built from user request
        """
        if self.settings.get("sync_ask") and \
                self.ask_yesno("dav_sync_ask", {"type": spoken_type}) == "no":
            alert.skip_sync = True
            return

        services = self.alert_manager.dav_services
        if len(services) == 1:
            alert.service = services[0]
            followup_dialog = "selection_dav_calendar"
        else:
            alert.service = self.ask_selection(services, "selection_dav_service")
            followup_dialog = ""

        calendar_dict = self.alert_manager.get_calendar_names()
        calendars = calendar_dict[alert.service]
        alert.calendar = (
            calendars[0]
            if len(calendars) == 1
            else self.ask_selection(calendars, followup_dialog)
        )

    def can_converse(self, message: Message) -> bool:
        """
        Determines if the skill can handle the given utterances in the specified language in the converse method.

        Override this method to implement custom logic for assessing whether the skill is capable of answering a query.

        Returns:
            True if the skill can handle the query during converse; otherwise, False.
        """
        if self.can_stop(message):  # same logic
            sess = SessionManager.get(message)
            for utterance in message.data.get("utterances", []):
                if (voc_match(utterance, "dismiss", lang=sess.lang, exact=True) or
                        voc_match(utterance, "snooze", lang=sess.lang)):
                    return True
        return False

    def converse(self, message: Message):
        """
        If there is an active alert, see if the user is trying to dismiss it
        """
        user_alerts = self.alert_manager.get_alerts()
        active: List[Alert] = user_alerts["active"]
        if active:
            LOG.debug(f"User has active alerts: {[a.alert_name for a in active]}")
            for utterance in message.data.get("utterances"):
                # dismiss
                if voc_match(utterance, "dismiss", self.lang, exact=True):
                    for alert in active:
                        self._dismiss_alert(alert.ident, speak=True)
                    break
                # snooze
                else:
                    message.data["utterance"] = utterance
                    token = tokenize_utterance(message)
                    snooze_duration = \
                        parse_timedelta_from_message(message, token,
                                                     timezone=active[0].timezone)
                    duration = snooze_duration or self.snooze_duration
                    _utterance = " ".join(token)
                    LOG.debug(f"cleared utterance: ({_utterance})")
                    if voc_match(_utterance, "snooze", self.lang, exact=True):
                        for alert in active:
                            self._snooze_alert(alert, snooze_duration)
                        self.speak_dialog("confirm_snooze_alert",
                                          {"duration": nice_duration(round(duration.total_seconds()),
                                                                     lang=self.lang)})
                        break
            else:
                # failed to understand what alert we should snooze/dismiss, prompt user to ask again
                self.speak_dialog("please.repeat", listen=True)

    def _get_response_cascade(self, dialog: str = "",
                              data: Optional[dict] = None,
                              message: Optional[Message] = None):

        data = data or dict()
        response = False
        items = []
        self.speak_dialog(dialog, data, wait=True)
        while response is not None:
            response = self.get_response(num_retries=0, message=message)
            if response:
                items.append(response)

        return items

    # Search methods
    def _resolve_requested_alert(
            self, message: Message,
            alert_type: AlertType,
            tokens=None,
            disposition: AlertState = AlertState.PENDING,
            dialog: str = "pick_multiple_entries"
    ) -> Optional[Alert]:
        """
        Resolve a valid requested alert from a user intent
        :param message: Message associated with the request
        :param alert_type: AlertType to consider
        :param alerts: List of Alert objects to resolve from
        :returns: best matched Alert from alerts or None
        """
        tokens = tokens or tokenize_utterance(message)
        requested_time, requested_name = parse_alert_name_and_time_from_message(message, tokens)

        alerts = self._get_alerts_list(alert_type,
                                       disposition=disposition)
        if not alerts:
            return None

        # List handling (except lists in the process of creation)
        if alert_type == AlertType.TODO and message.data.get("list") and \
                not message.data.get("create"):
            alerts = list(filter(lambda alert: alert.children, alerts))

        if message.data.get("next") or len(alerts) == 1:
            return alerts[0]
        elif not any((requested_name, requested_time)):
            return self._pick_one_by_name(alerts, dialog)

        # Iterate over all alerts to find a matching alert
        candidates = list()
        for alert in alerts:
            match_acc = None
            expiration = alert.expiration
            if requested_time and expiration == requested_time:
                match_acc = MatchLevel.DT_EXACT
            elif requested_time and expiration \
                    and expiration.time() == requested_time.time():
                match_acc = MatchLevel.TIME_EXACT
            if requested_name and alert.alert_name == requested_name:
                match_acc = (
                    MatchLevel.NAME_EXACT if match_acc is None else MatchLevel.ALL_EXACT
                )
            if match_acc is not None:
                candidates.append((match_acc, alert))
                continue
            # fuzzy_match aggregates ratio, partial_ratio and token_sort_ratio
            match_acc = fuzzy_match(alert.alert_name, requested_name)
            if match_acc >= 90:
                candidates.append((match_acc, alert,))
        if not candidates:
            return None

        candidates.sort(key=lambda match: match[0], reverse=True)
        return self._pick_one_by_name([alert for _, alert in candidates],
                                      dialog)

    def _pick_one_by_name(self, alerts: List[Alert], dialog: str = ""):
        """
        Narrow down a search list by asking the user which alert to pick (by alert_name)
        :param alerts: List of alerts to choose from
        :param dialog: which dialog to speak
        """
        if not alerts:
            return None
        elif len(alerts) > 1:
            spoken_list = [alert.alert_name for alert in alerts]
            self.speak_dialog(dialog, wait=True)
            choice = self.ask_selection(spoken_list, numeric=True)
            # retry with numbers
            if choice not in spoken_list:
                num = self.get_response(
                    "selection_not_understood",
                    validator=validate_number,
                    data={"max": len(spoken_list)}
                )
                if num:
                    choice = spoken_list[num - 1]
                else:
                    return None
            return alerts[spoken_list.index(choice)]
        return alerts[0]

    def _pick_one_by_time(self, alerts: List[Alert], dialog: str = ""):
        """
        Narrow down a search list by asking the user which alert to pick (by expiration)
        :param alerts: List of alerts to choose from
        :param dialog: which dialog to speak
        """
        if not alerts:
            return None
        # we have to create our own "ask selection", as there is no way to pick from
        # spoken datetimes
        if len(alerts) > 1:
            alerts.sort(key=lambda x: x.expiration)
            spoken_list = [
                f"{pronounce_number(i + 1)}. \
                    {nice_date_time(alert.expiration, use_24hour=self.use_24hour, use_ampm=not self.use_24hour, lang=self.lang)}"
                for i, alert in enumerate(alerts)
            ]
            self.speak(join_word_list(spoken_list, connector="and", sep=",", lang=self.lang), wait=True)
            idx = self.get_response("alert_list_choose_between",
                                    validator=validate_number,
                                    data=dict(length=len(spoken_list)))
            if idx:
                return alerts[idx - 1]
            return None
        return alerts[0]

    # Static parser methods
    def _event_get_alerts(self, message):
        """
        Handles a request to get scheduled events for a specified
        user and disposition.
        :param message: Message specifying 'user' (optional)
         and 'disposition' (pending/missed)
        """
        user = message.data.get("user")
        alert_type = message.data.get("alert_type", "all").upper()
        if alert_type not in AlertType.__members__:
            LOG.error(f"Invalid alert type requested: {alert_type}")
            self.bus.emit(message.response({"error": "Invalid alert type"}))
            return
        else:
            alert_type = AlertType[alert_type]
        disposition = message.data.get("disposition", "pending").upper()
        if disposition not in AlertState.__members__:
            LOG.error(f"Invalid disposition requested: {disposition}")
            self.bus.emit(message.response({"error": "Invalid disposition"}))
            return
        else:
            disposition = AlertState[disposition]

        matched = self._get_alerts_list(alert_type,
                                        user,
                                        disposition)

        data = {alert.ident: alert.serialize for alert in matched}
        self.bus.emit(message.response(data))

    def _get_alerts_list(self,
                         alert_type: AlertType,
                         user: str = None,
                         disposition: AlertState = AlertState.PENDING,
                         name: str = "") -> List[Alert]:
        """
        Get all alerts matching the requested criteria and a spoken type
        :param user: user requesting alerts or None to get all alerts
        :param alert_type: AlertType to return (AlertType.ALL for all)
        :param disposition: AlertState to filter by
        :returns: list of matched alerts, str speakable alert type
        """
        user = user or LOCAL_USER
        alerts_list = self.alert_manager.get_alerts(user, alert_type)

        # Determine alerts list based on disposition
        if disposition == AlertState.PENDING:
            matched_alerts = alerts_list["pending"]
        elif disposition == AlertState.ACTIVE:
            matched_alerts = alerts_list["active"]
        elif disposition == AlertState.MISSED:
            matched_alerts = alerts_list["missed"]
        else:
            LOG.error(f"Invalid alert disposition requested: {disposition}")
            matched_alerts = alerts_list["pending"]

        # Optionally filter by name
        if name:
            matched_alerts = list(
                filter(
                    lambda alert: fuzzy_match(alert.alert_name, name, 90),
                    matched_alerts
                )
            )
        return matched_alerts

    # GUI methods
    def _display_alert(self, alert: Alert):
        return self._display_alerts(alert.alert_type, [alert])

    def _display_alerts(self, alert_type: AlertType, alerts: Optional[List[Alert]] = None):
        if alerts is None:
            alerts = self.alert_manager.get_pending_alerts(alert_type=alert_type)

        if alert_type == AlertType.ALARM:
            self._display_alarms(alerts)
        elif alert_type == AlertType.TIMER:
            self._display_timers(alerts)
        elif alert_type != AlertType.ALL:
            self._display_list(alerts, header=spoken_alert_type(alert_type))

    def _display_alarms(self, alarms: List[Alert]):
        """
        Create a GUI view with the passed list of alarms shown immediately
        :param alarms: List of alarm type Alerts to display
        """
        alarms_view = list()
        for alarm in alarms:
            alarms_view.append(build_gui_data(alarm))

        self.gui['activeAlarmCount'] = len(alarms_view)
        self.gui['activeAlarms'] = alarms_view

        if any([alarm.is_expired for alarm in alarms]):
            override = True
        else:
            # Show created alarm UI for some set duration
            override = 30
        self.gui.show_page("AlarmsOverviewCard", override_idle=override)

    def _display_timers(self, timers: List[Alert]):
        """
        Create a GUI view with the passed list of timers shown immediately
        :param timers: List of timer type Alerts to display
        """
        for timer in timers:
            if not any((timer.ident == active.ident for active in
                        self.alert_manager.active_gui_timers)):
                self.alert_manager.add_timer_to_gui(timer)

        # already an active gui page
        if self.gui.page == "Timer":
            return

        self.gui.show_page("Timer", override_idle=True)
        create_daemon(self._start_timer_gui_thread)

    def _display_list(self, alerts: List[Alert], header: str = "Todo"):
        """
        Create a GUI view with the passed list of alerts shown immediately

        :param timers: List of todo type Alerts to display
        :param header: Header to display above the list
        """
        # Based on type main and secondary are populated as see fit
        # The list entry view is split into two sections if `secondary` is not ""
        # otherwise only main is shown as list entry
        # -----------------------------------------------
        # |             Main (focussed)                 |
        # -----------------------------------------------
        # |                Secondary                    |
        # -----------------------------------------------
        # 
        # -----------------------------------------------
        # |                                             |
        # |                 Main                        |
        # |                                             |
        # -----------------------------------------------

        self.gui["items"] = [
            {
                "main": alert.alert_name,
                "secondary": ""
                if alert.expiration is None
                else datetime_display(alert.expiration, alert.until, alert.lang),
            }
            for alert in alerts
        ]
        self.gui["header"] = header
        self.gui.show_page("ListView")

    def _update_homescreen(self, alert: Alert = None, dismiss_notification=False):
        """
        Update homescreen widgets with the current alarms and timers counts.

        :param alert: the alert to update the homescreen widgets for (default: only refresh widgets)
        :param dismiss_notification: whether or not to dismiss the notification
                                     of the passed alert (default: add notification)
        """
        self._update_homescreen_widgets(alert)
        if dismiss_notification:
            self._delete_homescreen_notification(alert)

    def _update_homescreen_widgets(self, alert: Alert = None):
        # timer widget
        if alert is None or alert.alert_type == AlertType.TIMER:
            widget_data = {"count": len(self.alert_manager.active_gui_timers),
                           "action": "ovos.gui.show.pending.timers"}
            self.bus.emit(Message("ovos.widgets.update",
                                  {"type": "timer", "data": widget_data}))
        # alarm widget
        if alert is None or alert.alert_type == AlertType.ALARM:
            alarms = \
                self.alert_manager.get_alerts(alert_type=AlertType.ALARM)
            pending = alarms['pending']
            widget_data = {"count": len(pending),
                           "action": "ovos.gui.show.pending.alarms"}
            self.bus.emit(Message("ovos.widgets.update",
                                  {"type": "alarm", "data": widget_data}))
        # missed alert widget
        if alert is None:
            missed = self.alert_manager.get_alerts()['missed']
            for alert in missed:
                self._create_homescreen_notification(alert)

    def _create_homescreen_notification(self, alert: Alert, duration: int = 0):
        spoken_type = spoken_alert_type(alert.alert_type).title()
        noticetype = 'transient'
        if duration and alert.priority > AlertPriority.AVERAGE:
            noticetype = 'sticky'
        LOG.debug(f'add notification: {spoken_type}: {alert.alert_name}')
        self.gui.show_notification(content=f'{spoken_type}: {alert.alert_name}',
                                   duration=duration,
                                   action='ovos.alerts.dismiss_notification',
                                   noticetype=noticetype,
                                   callback_data={'alert': alert.data})

    def _delete_homescreen_notification(self, alert: Alert):
        if alert is None:
            return LOG.error("tried to delete alert notification of 'None' alert")
        spoken_type = spoken_alert_type(alert.alert_type).title()
        # sender/text are minimum requirements to be deleteable
        notification_data = {
            "sender": self.skill_id,
            "text": f"{spoken_type}: {alert.alert_name}"
        }
        LOG.debug(f'delete notification: {notification_data}')
        self.bus.emit(Message("ovos.notification.api.storage.clear.item",
                              {"notification": notification_data}))

    def _on_display_gui(self, message: Message):
        """
        Handle Messages requesting display of GUI
        :param message: Message associated with GUI display request
        """
        if message.msg_type == "ovos.gui.show.active.timers":
            self._display_alerts(AlertType.TIMER)
        elif message.msg_type == "ovos.gui.show.active.alarms":
            self._display_alerts(AlertType.ALARM)
        else:
            raise ValueError(f"Invalid GUI display request: {message.msg_type}")

    def _start_timer_gui_thread(self):
        """
        Start updating the Timer UI while there are still active timers and
        refresh them every second.
        """
        if not self._gui_timer_lock.acquire(True, 1):
            return
        while self.alert_manager.active_gui_timers:
            timers_to_display = self.alert_manager.active_gui_timers[:10]
            if timers_to_display:
                display_data = [build_gui_data(timer)
                                for timer in timers_to_display]
                self.gui['activeTimers'] = {'timers': display_data}
            time.sleep(1)
        self._gui_timer_lock.release()
        self.gui.release()

    def _gui_cancel_timer(self, message: Message):
        """
        Handle a GUI timer dismissal
        """
        alert_id = message.data['timer']['alertId']
        self._dismiss_alert(alert_id, speak=True)
        LOG.debug(f"Timers still active on GUI: {self.alert_manager.active_gui_timers}")

    def _event_cancel_alarm(self, message: Message):
        """
        Handle a alarm dismissal per event
        """
        alert_ids = message.data.get('alarmIndex')
        if alert_ids is None:
            self.alert_manager.get_active_alerts(alert_type=AlertType.ALARM)
        elif isinstance(alert_ids, str):
            alert_ids = [alert_ids]
        for alert_id in alert_ids:
            self._dismiss_alert(alert_id, speak=True)

    def _release_gui_alarm(self, alert_id: str):
        alarm = self.alert_manager.get_alert(alert_id)
        if self.gui.get('activeAlarms'):
            # Multi Alarm view
            for active in self.gui.get('activeAlarms'):
                if active.get('alarmIndex') == alert_id:
                    self.gui['activeAlarms'].remove(active)
                    break
            self.gui['activeAlarmCount'] = len(self.gui['activeAlarms'])
            # dont release gui on multi alert or timers up
            if self.gui['activeAlarmCount'] != 0 or \
                    self.alert_manager.active_gui_timers:
                return

        if len(self.gui._pages) > 1:
            self.gui.remove_page("AlarmsOverviewCard")
        else:
            self.gui.release()
            # minimize OCP
            if alarm.ocp_request:
                self.bus.emit(Message("system.display.homescreen", {}))

    def _event_snooze_alarm(self, message):
        """
        Handle a alarm snooze per event
        """
        alert_ids = message.data.get('alarmIndex')
        if alert_ids is None:
            self.alert_manager.get_active_alerts(alert_type=AlertType.ALARM)
        elif isinstance(alert_ids, str):
            alert_ids = [alert_ids]
        for alert_id in alert_ids:
            alert = self.alert_manager.get_alert(alert_id)
            LOG.info(f"GUI Snooze alert: {alert_id}")
            self._snooze_alert(alert)
            self.speak_dialog("confirm_snooze_alert",
                              {"name": alert.alert_name,
                               "duration": nice_duration(self.snooze_duration, lang=self.lang)},
                              wait=True)

    def _gui_dismiss_notification(self, message):
        """
        Handles GUI notification dismissal for an alert.
        
        If the alert is active, removes it and confirms dismissal via dialog. If the alert is missed, removes it without confirmation. Always deletes the corresponding homescreen notification.
        """
        if not message.data.get('alert'):
            LOG.error("Outdated Notification, unable to dismiss")
            return
        alert = Alert.from_dict(message.data['alert'])
        alert_id = alert.ident
        if alert_id in self.alert_manager.active_alerts:
            self.alert_manager.rm_alert(alert_id)
            self.speak_dialog("confirm_dismiss_alert",
                              {"kind": spoken_alert_type(alert.alert_type)})
        elif alert_id in self.alert_manager.missed_alerts:
            #self.alert_manager.dismiss_missed_alert(alert_id)
            self.alert_manager.rm_alert(alert_id)
        # the notification has to be explicitly removed to not force the user to
        # additionally push the trashbin button
        # TODO: remove with https://github.com/OpenVoiceOS/ovos-skill-homescreen/pull/92
        self._delete_homescreen_notification(alert)

    def _display_expiration(self, alert: Alert):
        """
        Displays the expiration notification for a given alert in the GUI.
        
        If the alert is a reminder or event, creates a homescreen notification with a timeout; otherwise, displays the alert without a notification timeout.
        """
        should_display = alert.alert_type in (AlertType.REMINDER, AlertType.EVENT)
        # This is solely due to reminder/event not having a proper ui element
        # changes in the future 
        notify_duration = self.alert_timeout_seconds if should_display else 0
        self._create_homescreen_notification(alert, notify_duration)
        self._display_alert(alert)

    # Handlers for expiring alerts
    def _alert_prenotification(self, alert: Alert):
        """
        Callback for AlertManager on Alert prenotification
        :param alert: expired Alert object
        """
        # As with alert expiration, loop the text and send notification
        # to homescreen if not conversed

        timeout = time.time() + self.alert_timeout_seconds
        alert_id = alert.ident
        while self.alert_manager.get_alert_status(alert_id) == \
                AlertState.ACTIVE and time.time() < timeout:
            self.speak_dialog(
                "alert_prenotification",
                {
                    "reminder": alert.alert_name,
                    "time_until": nice_duration(alert.time_to_expiration, lang=self.lang),
                },
            )
            time.sleep(min(20, self.alert_timeout_seconds))
        if self.alert_manager.get_alert_status(alert_id) == AlertState.ACTIVE:
            self.alert_manager.mark_alert_missed(alert_id)
            self._create_homescreen_notification(alert)

    def _alert_expired(self, alert: Alert):
        """
        Callback for AlertManager on Alert expiration
        :param alert: expired Alert object
        """
        self._activate()

        if alert.ocp_request or alert.audio_file:
            self._play_notify_expired(alert)
        elif alert.alert_type == AlertType.ALARM and not self.speak_alarm:
            self._play_notify_expired(alert)
        elif alert.alert_type == AlertType.TIMER and not self.speak_timer:
            self._play_notify_expired(alert)
        else:
            self._speak_notify_expired(alert)

        # ocp alerts/timer kept active until conversed (snooze/dismiss)
        # (or handled per GUI)
        if alert.ocp_request or alert.alert_type == AlertType.TIMER:
            return

        if self.alert_manager.get_alert_status(alert.ident) == AlertState.ACTIVE:
            self.alert_manager.mark_alert_missed(alert.ident)

    def _play_notify_expired(self, alert: Alert):
        """
        Handle audio playback on alert expiration
        :param alert: Alert that has expired
        """
        # volume handling
        self.original_volume = self.bus.wait_for_response(
            Message("mycroft.volume.get")
        ) or 100
        secs_played = 0
        timeout = self.alert_timeout_seconds
        max_volume = self.play_volume
        escalate = self.settings.get("escalate_volume")
        if alert.alert_type == AlertType.TIMER:
            escalate = False

        if escalate:
            volume = 0.1
            # half of the time play on full loudness, increments of 10% vol
            steps = int(timeout / 2 / ((max_volume - volume) / 0.1))
        else:
            volume = max_volume
        self.bus.emit(Message("mycroft.volume.set", {"percent": volume}))

        alert_id = alert.ident

        # check if a ocp request is successful
        # if request can't be served, fallback to default behaviour
        if alert.media_type in ("ocp", "file"):
            to_play = "ocp"
            # send ocp request
            if ocp_request(alert, self.bus) is None:
                alert.ocp_request = None

        if not alert.ocp_request:
            if alert.audio_file:
                LOG.debug(alert.audio_file)
                self.speak_dialog("expired_audio_alert_intro", wait=True)
                to_play = self.find_resource(alert.audio_file, "snd")
            elif alert.alert_type == AlertType.ALARM:
                to_play = self.alarm_sound_file
            elif alert.alert_type == AlertType.TIMER:
                to_play = self.timer_sound_file
            else:
                LOG.error(f"Audio File Not Specified")
                to_play = None

            if not to_play:
                self._speak_notify_expired(alert)
                return

        # display card and register with notification system
        self._display_expiration(alert)

        while self.alert_manager.get_alert_status(alert_id) == \
                AlertState.ACTIVE and secs_played < timeout:
            secs_played += 1
            if escalate and secs_played % steps == 0 \
                    and volume < max_volume:
                volume_step = min(0.1, self.play_volume - volume)
                volume = round(volume + volume_step, 2)
                _data = {'play_sound': False}
                if volume_step != 0.1:
                    _data["percent"] = volume_step
                self.bus.emit(Message("mycroft.volume.increase", _data))
            if not to_play == "ocp":
                play_audio(to_play).wait(60)
            # TODO this depends on the length of the audio file
            time.sleep(1)

        # reset volume
        if not to_play == "ocp":
            self.bus.emit(Message("mycroft.volume.set", {"percent": self.original_volume}))

    def _speak_notify_expired(self, alert: Alert):

        LOG.debug(f"notify alert expired: {alert.ident}")

        self._display_expiration(alert)

        # Notify user until they dismiss the alert
        timeout = time.time() + self.alert_timeout_seconds
        alert_id = alert.ident

        # if default name, replace alert_type substring
        alert_type = spoken_alert_type(alert.alert_type)
        name = alert.alert_name.replace(alert_type, "")
        LOG.debug(f"State: {self.alert_manager.get_alert_status(alert_id)}")
        while self.alert_manager.get_alert_status(alert_id) == \
                AlertState.ACTIVE and time.time() < timeout:
            LOG.debug("Triggered speech")
            if alert.alert_type in (AlertType.REMINDER, AlertType.EVENT,):
                self.speak_dialog('expired_reminder',
                                  {'name': name},
                                  wait=True)
            elif alert.alert_type == AlertType.TIMER:
                self.speak_dialog('expired_timer',
                                  {'name': name},
                                  wait=True)
            else:
                self.speak_dialog('expired_alert', {'name': name},
                                  wait=True)
            time.sleep(20)

    def _ocp_query(self, message: Message):
        kind = message.data.get("media", "media")
        result = None
        dialog = "alarm_ocp_request"

        while result is None:
            query = self.get_response(dialog, {"kind": kind})
            if query is None or voc_match("cancel", query, self.lang):
                break

            if dialog == "alarm_ocp_request":
                self.speak_dialog("ocp_searching")

            normalizer = UtteranceNormalizerPlugin.get_normalizer(lang=self.lang)
            query = normalizer.normalize(query)
            result = ocp_query(query, message, self.bus)
            if result is None:
                dialog = "ocp_request_retry"
        return result

    def _snooze_alert(self, alert: Alert, duration: Optional[timedelta] = None):
        """
        Helper to snooze an alert for the specified duration calling the
        alert manager, update widgets and handle media state
        :param alert: Alert to snooze
        :param snooze_duration (optional): Duration in seconds to snooze alert for
        """
        duration = duration or self.snooze_duration
        self._delete_homescreen_notification(alert)
        if alert.alert_type == AlertType.ALARM:
            if not self.speak_alarm:
                self.bus.emit(Message("mycroft.volume.set",
                                      {"percent": self.original_volume}))
            if alert.ocp_request:
                self.bus.emit(Message("ovos.common_play.stop", {}))
            self._release_gui_alarm(alert.ident)
        elif alert.alert_type == AlertType.TIMER:
            if not self.speak_timer:
                self.bus.emit(Message("mycroft.volume.set",
                                      {"percent": self.original_volume}))

        snoozed_alert = self.alert_manager.snooze_alert(alert.ident,
                                                        duration)
        self._update_homescreen(snoozed_alert)
        # deativate skill if no more active alerts
        if not self.alert_manager.get_active_alerts():
            self.deactivate()

    def _dismiss_alert(self, alert_id: str, drop_dav: bool = False, speak: bool = False):
        """
        Handle a request to dismiss an alert. Removes the first valid entry in
        active, missed, or pending lists.
        Also handles GUI pages and homescreen widgets

        :param alert_id: ID of alert to dismiss
        :param drop_dav: if True, remove from DAV service
        :param speak: if True, speak confirmation of alert dismissal
        """
        alert = self.alert_manager.get_alert(alert_id)
        disposition = self.alert_manager.get_alert_status(alert_id)
        if disposition == AlertState.REMOVED:
            LOG.debug(f"{alert_id} already removed")
            return

        # release from gui
        if alert.alert_type == AlertType.TIMER:
            self.alert_manager.dismiss_alert_from_gui(alert_id)
            if disposition == AlertState.ACTIVE and not self.speak_timer:
                self.bus.emit(Message("mycroft.volume.set",
                                      {"percent": self.original_volume}))
        elif alert.alert_type == AlertType.ALARM:
            if disposition == AlertState.ACTIVE and not self.speak_alarm:
                self.bus.emit(Message("mycroft.volume.set",
                                      {"percent": self.original_volume}))
            # stop ocp alarm
            if alert.ocp_request and alert.is_expired:
                self.bus.emit(Message("ovos.common_play.stop", {}))
            self._release_gui_alarm(alert_id)

        self.alert_manager.rm_alert(alert_id, disposition, drop_dav)
        self._update_homescreen(alert, dismiss_notification=True)

        if speak:
            self.speak_dialog("confirm_dismiss_alert",
                              {"kind": spoken_alert_type(alert.alert_type)},
                              wait=True)
            if alert.stopwatch_mode:
                self.speak_dialog("stopwatch_delta",
                                  {"delta": spoken_duration(alert.stopwatch)})

        # deativate skill if no more active alerts
        if not self.alert_manager.get_active_alerts():
            self.deactivate()

    def _activate(self):
        """
        Activate the skill
        """
        timeout = self.config_core["skills"].get("converse", {}).get("timeout", 300) - 2
        # repeating event to check if a reactivation is needed
        self.schedule_repeating_event(self.handle_active_state,
                                      when=None,
                                      frequency=timeout,
                                      name="check_active_state")
        self.activate()

    def handle_active_state(self, message: Message):
        """
        Check if there are active alerts and reactivate the skill
        :param message: Message associated with the request
        """
        # If there are active alerts, reactivate
        if self.alert_manager.get_active_alerts():
            LOG.debug("Reactivating skill due to active alerts")
            self.activate()
        else:
            self.cancel_scheduled_event("check_active_state")

    def handle_deactivate(self, message: Message):
        """
        Handle deactivation messages from the intent service
        :param message: Message associated with the request
        """
        # to make sure the intent handler not accidentally triggers deactivate
        self.handle_active_state(message)

    def shutdown(self):
        """
        Shuts down the skill, marking all active alerts as missed and clearing the GUI.
        """
        LOG.debug(f"Shutdown, all active alerts are now missed")
        self.alert_manager.shutdown()
        self.gui.clear()

    def can_stop(self, message: Message) -> bool:
        user_alerts = self.alert_manager.get_alerts()
        active: List[Alert] = user_alerts["active"]
        return bool(active)

    def stop(self):
        """
        Stops all active alerts and returns whether any were stopped.
        
        Returns:
            bool: True if any active alerts were dismissed, False otherwise.
        """
        # TODO - session support, timer per user
        LOG.debug(f"skill-stop called, all active alerts will be removed")
        stopped = False
        for alert in self.alert_manager.get_active_alerts():
            self._dismiss_alert(alert.ident, speak=True)
            stopped = True
        return stopped
