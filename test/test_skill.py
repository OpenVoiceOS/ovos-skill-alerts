# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Regina Bloomstine, Elon Gasper, Richard Leeds
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2021: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

import datetime as dt
import json
from uuid import uuid4
import random
import shutil
import unittest
from os import mkdir, remove
from os.path import dirname, join, exists, isfile
from threading import Event
from typing import Set, Union, List, Optional
import time
from copy import deepcopy

from dateutil.tz import tzlocal
import pytest
import icalendar
from json_database import JsonStorage
from mock import Mock, patch
from mock.mock import call
from ovos_date_parser import nice_time, nice_date_time, nice_duration
from ovos_number_parser import pronounce_number
from ovos_bus_client.message import Message
from ovos_utils.events import EventSchedulerInterface
from ovos_utils.messagebus import FakeBus
from ovos_workshop.skills import OVOSSkill

from ovos_config.locale import load_language, get_default_tz

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertPriority, AlertState, AlertType, DAVType, Weekdays, EVERYDAY
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.alert_manager import AlertManager
from ovos_skill_alerts.util.locale import spoken_duration, get_alert_dialog_data


examples_dir = join(dirname(__file__), "example_messages")

SETTINGS = {
    "speak_alarm": False,
    "speak_timer": True,
    "sound_alarm": "constant_beep.mp3",
    "sound_timer": "beep4.mp3",
    "snooze_mins": 15,
    "timeout_min": 2,
    "priority_cutoff": 8,
    "services": "",
    "frequency": 15,
    "sync_ask": False
}


def _get_message_from_file(filename: str):
    with open(join(examples_dir, filename)) as f:
        contents = f.read()
    msg = Message.deserialize(contents)
    msg.context["timing"]["handle_utterance"] = time.time()
    return msg


def sleep_until_full_second():
    now = dt.datetime.now()
    next_second = now + dt.timedelta(seconds=1)
    time.sleep((next_second - now).total_seconds())
    return dt.datetime.now(tzlocal()).replace(microsecond=0)


def change_user_tz(message: Message, tz):
    message.context["username"] = "test_user"
    message.context["user_profiles"] = [{"user": {"username": "test_user"},
                                        "location": {"tz": tz}}]

def now_time(tz=None):
    tz = tz or get_default_tz()
    now = dt.datetime.now(tz).replace(microsecond=0)

    # problem: the skill uses multiple conversions between dt <> isoformat
    # resulting in tz being dt.timedelta. this is to ease the pain with asserting dts
    iso = now.isoformat()
    return dt.datetime.fromisoformat(iso)

@unittest.skip('Work in progress')
class TestSkill(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        #from mycroft.skills.skill_loader import SkillLoader

        cls.bus = FakeBus()
        cls.bus.run_in_thread()

        cls.test_fs = join(dirname(__file__), "test_cache")
        if not exists(cls.test_fs):
            mkdir(cls.test_fs)
        settings = JsonStorage(join(cls.test_fs, "settings.json"))
        settings.merge(SETTINGS)

        cls.skill = AlertSkill(bus=cls.bus,
                               skill_id="skill-alerts.openvoiceos",
                               settings=settings,
                               alerts_path=cls.test_fs)
        cls.skill.initialize()

        # Override to test passed arguments / get back a pre defined return value
        # defined in the respective tests
        cls.skill.speak = Mock()
        cls.skill.speak_dialog = Mock()
        cls.skill.ask_yesno = Mock()
        cls.skill.get_response = Mock()
        cls.skill.ask_selection = Mock()
        cls.skill._get_response_cascade = Mock()
        cls.skill.ask_for_prenotification = Mock()
        cls.skill.alert_manager.get_dav_calendar = Mock(return_value=FakeCalendar())
        cls.skill.alert_manager.get_dav_calendars = Mock(return_value=[FakeCalendar()])

        # Setup alerts
        load_language("en-us")

        uuid_subitem1 = str(uuid4())
        uuid_subitem2 = str(uuid4())
        uuid_parent = str(uuid4())

        default_tz = get_default_tz()

        now_time = dt.datetime.now(default_tz).replace(microsecond=0)
        past_alarm_time = now_time + dt.timedelta(minutes=-1)
        next_alarm_1_time = now_time + dt.timedelta(days=1)
        next_alarm_2_time = next_alarm_1_time + dt.timedelta(hours=1)
        next_alarm_3_time = next_alarm_2_time + dt.timedelta(minutes=1)
        next_reminder_time = now_time + dt.timedelta(days=2)
        next_reminder_until = now_time + dt.timedelta(
            days=2, hours=2
        )  # ie 2 hour event
        next_timer_time = now_time + dt.timedelta(minutes=1)

        cls.past_alarm = Alert.create(
            expiration=past_alarm_time,
            alert_name="past alarm",
            alert_type=AlertType.ALARM
        )
        cls.valid_alarm_1 = Alert.create(
            expiration=next_alarm_1_time,
            alert_name="alarm 1",
            alert_type=AlertType.ALARM
        )
        cls.valid_alarm_2 = Alert.create(
            expiration=next_alarm_2_time,
            alert_name="alarm 2",
            alert_type=AlertType.ALARM
        )
        cls.valid_alarm_3 = Alert.create(
            expiration=next_alarm_3_time,
            alert_name="alarm 3",
            alert_type=AlertType.ALARM
        )
        cls.valid_reminder = Alert.create(
            expiration=next_reminder_time,
            alert_name="walk dog",
            alert_type=AlertType.REMINDER,
            dav_type=DAVType.VEVENT,
            until=next_reminder_until
        )
        # event w/ length
        cls.valid_event = Alert.create(
            expiration=next_reminder_time,
            alert_name="valid event",
            alert_type=AlertType.EVENT,
            dav_type=DAVType.VEVENT,
            until=next_reminder_until
        )
        # event w/o length
        cls.valid_event2 = Alert.create(
            expiration=now_time + dt.timedelta(days=1, hours=1),
            alert_name="valid event 2",
            alert_type=AlertType.EVENT,
            dav_type=DAVType.VEVENT
        )
        cls.shopping_list = Alert.create(
            alert_name="shopping",
            alert_type=AlertType.TODO,
            context=dict(
                parent_to=[uuid_subitem1, uuid_subitem2],
                ident=uuid_parent,
            ),
        )
        cls.shopping_subitem1 = Alert.create(
            alert_name="mango",
            alert_type=AlertType.TODO,
            context=dict(
                related_to=uuid_parent, ident=uuid_subitem1
            ),
        )
        cls.shopping_subitem2 = Alert.create(
            alert_name="butter",
            alert_type=AlertType.TODO,
            context=dict(
                related_to=uuid_parent, ident=uuid_subitem2
            ),
        )
        cls.dummy_list = Alert.create(
            alert_name="dummy_list",
            alert_type=AlertType.TODO,
            context=dict(
                parent_to=["dummy_subitem"],
                ident="dummy_id",
            ),
        )
        cls.todo_reminder = Alert.create(
            alert_name="flowers",
            alert_type=AlertType.TODO
        )
        cls.reschedule_event1 = Alert.create(
            expiration=now_time+dt.timedelta(hours=1),
            alert_name="Tennis",
            alert_type=AlertType.EVENT
        )
        cls.reschedule_event2 = Alert.create(
            expiration=now_time+dt.timedelta(hours=2),
            alert_name="baseball training",
            repeat_days=EVERYDAY,
            alert_type=AlertType.EVENT
        )
        cls.valid_timer = Alert.create(
            expiration=next_timer_time,
            alert_name="oven",
            alert_type=AlertType.TIMER
        )       
        cls.now_time = now_time

        # make sure storage empty
        cls.skill.alert_manager._alerts_store.clear()
        cls.skill.alert_manager._alerts_store.store()

    def populate_alerts(self, alerts: Optional[List[Alert]] = None,
                              exception: Optional[AlertType] = None):
        alerts = alerts or [self.valid_timer,
                            self.valid_reminder,
                            self.valid_event,
                            self.valid_event2,
                            self.shopping_list,
                            self.shopping_subitem1,
                            self.shopping_subitem2,
                            self.dummy_list,
                            self.todo_reminder,
                            self.valid_alarm_3,
                            self.valid_alarm_1,
                            self.valid_alarm_2,
                            self.reschedule_event1,
                            self.reschedule_event2]
        for a in alerts:
            if a.alert_type == exception:
                continue
            self.skill.alert_manager.add_alert(a)
    
    def reset_alert_manager(self):
        self.tearDown()
        self.skill.initialize()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.test_fs)

    def tearDown(self) -> None:
        self.skill.alert_manager._alerts_store.clear()
        self.skill.alert_manager._alerts_store.store()
        self.skill.speak.reset_mock(return_value=True)
        self.skill.speak_dialog.reset_mock(return_value=True)
        self.skill.ask_yesno.reset_mock(return_value=True)
        self.skill.get_response.reset_mock(return_value=True)
        self.skill.ask_selection.reset_mock(return_value=True)
        self.skill._get_response_cascade.reset_mock(return_value=True)
        self.skill.ask_for_prenotification.reset_mock(return_value=True)

    def test_00_skill_init(self):
        # Test any parameters expected to be set in init or initialize methods

        self.assertIsInstance(self.skill, OVOSSkill)
        # TODO: This patches import resolution; revert after proper packaging
        self.assertIsInstance(self.skill.alert_manager, AlertManager)
        self.assertTrue(hasattr(self.skill.alert_manager, "pending_alerts"))

    def test_properties(self):
        
        # speak_alarm
        self.assertFalse(self.skill.speak_alarm)
        self.skill.settings["speak_alarm"] = True
        self.assertTrue(self.skill.speak_alarm)
        self.skill.settings["speak_alarm"] = False
        self.assertFalse(self.skill.speak_alarm)

        # speak_timer
        self.assertTrue(self.skill.speak_timer)
        self.skill.settings["speak_timer"] = False
        self.assertFalse(self.skill.speak_timer)
        self.skill.settings["speak_timer"] = True
        self.assertTrue(self.skill.speak_timer)

        # alarm_sound_file
        self.assertTrue(isfile(self.skill.alarm_sound_file))
        test_file = join(dirname(__file__), "test_sounds", "alarm.mp3")
        self.skill.settings["sound_alarm"] = test_file
        self.assertEqual(self.skill.alarm_sound_file, test_file)

        # timer_sound_file
        self.assertTrue(isfile(self.skill.timer_sound_file))
        test_file = join(dirname(__file__), "test_sounds", "timer.mp3")
        self.skill.settings["sound_timer"] = test_file
        self.assertEqual(self.skill.timer_sound_file, test_file)

        # snooze_duration
        self.assertEqual(self.skill.snooze_duration, dt.timedelta(minutes=15))
        self.skill.settings["snooze_mins"] = 5
        self.assertEqual(self.skill.snooze_duration, dt.timedelta(minutes=5))
        self.skill.settings["snooze_mins"] = "10"
        self.assertEqual(self.skill.snooze_duration, dt.timedelta(minutes=15))

        # alert_timeout_seconds
        self.assertEqual(self.skill.alert_timeout_seconds, 120)
        self.skill.settings["timeout_min"] = 0.5
        self.assertEqual(self.skill.alert_timeout_seconds, 30)
        self.skill.settings["timeout_min"] = "5"
        self.assertEqual(self.skill.alert_timeout_seconds, 60)

        # use_24hour
        self.assertIsInstance(self.skill.use_24hour, bool)
        # TODO: Better test here

    def test_handle_create_alarm(self):
        real_confirm = self.skill.confirm_alert
        confirm_alert = Mock()
        self.skill.confirm_alert = confirm_alert
        valid_message = _get_message_from_file("create_alarm_daily.json")
        invalid_message = _get_message_from_file(
            "invalid_messages/create_alarm_no_time.json"
        )

        self.skill.handle_create_alarm(invalid_message)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "error_no_time", {"kind": "alarm"}, wait=True
        )
        self.skill.speak_dialog.reset_mock()
        self.skill.confirm_alert.assert_not_called()

        self.skill.handle_create_alarm(valid_message)
        self.skill.confirm_alert.assert_called_once()
        self.assertEqual(
            self.skill.confirm_alert.call_args[0][0].alert_type, AlertType.ALARM
        )
        self.assertEqual(self.skill.confirm_alert.call_args[0][1], valid_message)

        self.skill.confirm_alert = real_confirm
        
        self.skill.confirm_alert(self.past_alarm, valid_message)
        self.skill.speak_dialog.assert_called_with("alert_expiration_past")

        self.reset_alert_manager()

    def test_handle_create_timer(self):
        real_confirm = self.skill.confirm_alert
        self.skill.confirm_alert = Mock()
        valid_timer = _get_message_from_file("set_time_timer.json")
        invalid_timer = _get_message_from_file(
            "invalid_messages/create_timer_no_duration.json"
        )

        self.skill.handle_create_timer(invalid_timer)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with("error_no_duration", wait=True)
        self.skill.confirm_alert.assert_not_called()

        self.skill.handle_create_timer(valid_timer)
        self.skill.confirm_alert.assert_called_once()
        self.assertEqual(
            self.skill.confirm_alert.call_args[0][0].alert_type, AlertType.TIMER
        )
        self.assertEqual(self.skill.confirm_alert.call_args[0][1], valid_timer)
        self.skill.confirm_alert = real_confirm
        
        self.reset_alert_manager()

    def test_handle_create_reminder(self):
        real_confirm = self.skill.confirm_alert
        real_handle_create_todo = self.skill.handle_create_todo
        self.skill.confirm_alert = Mock()
        self.skill.get_response.return_value="no"
        self.skill.ask_yesno.return_value="no"
        self.skill.handle_create_todo = Mock()
        reminder_message = _get_message_from_file("reminder_at_time_to_action.json")
        todo_message = _get_message_from_file("reminder_no_time.json")

        self.skill.handle_create_reminder(reminder_message)
        self.skill.confirm_alert.assert_called_once()
        self.assertEqual(
            self.skill.confirm_alert.call_args[0][0].alert_type, AlertType.REMINDER
        )
        self.assertEqual(
            self.skill.confirm_alert.call_args[0][0].dav_type, DAVType.VEVENT
        )
        self.assertEqual(self.skill.confirm_alert.call_args[0][1], reminder_message)
        self.skill.confirm_alert.reset_mock()

        self.skill.handle_create_reminder(todo_message)
        self.skill.get_response.assert_called_once()
        # without datetime (even after reassuring callback) -> todo
        self.skill.handle_create_todo.assert_called_once()

        self.skill.confirm_alert = real_confirm
        self.skill.handle_create_todo = real_handle_create_todo
        
        self.reset_alert_manager()

    def test_handle_create_reminder_alt(self):
        real_method = self.skill.handle_create_reminder
        create_reminder = Mock()
        self.skill.handle_create_reminder = create_reminder
        test_message = Message("test", {"data": True}, {"context": "test"})
        self.skill.handle_create_reminder_alt(test_message)
        create_reminder.assert_called_once()
        create_reminder.assert_called_with(test_message)

        self.skill.handle_create_reminder = real_method
        
        self.reset_alert_manager()

    def test_handle_create_event(self):
        self.populate_alerts()

        real_confirm = self.skill.confirm_alert
        self.skill.get_response.return_value="no"
        self.skill.ask_yesno.return_value="no"
        self.skill.confirm_alert = Mock()
        # at the same time an overlapping event with "valid event"
        overlapping_reminder = _get_message_from_file(
            "reminder_event_length_at_time.json"
        )
        begin = nice_time(self.valid_event.expiration)
        end = nice_time(self.valid_event.until)
        self.skill.handle_create_event(overlapping_reminder)
        self.skill.ask_yesno.assert_called_once()
        self.skill.ask_yesno.assert_called_with(
            "alert_overlapping_duration_ask", {"event": "valid event",
                                               "begin": begin,
                                               "end": end}
        )
        # the reminder is dropped by the user due to overlap
        self.skill.ask_for_prenotification.assert_not_called()
        self.skill.confirm_alert.assert_not_called()

        self.skill.ask_yesno.reset_mock()
        # overlapping event with no end time
        overlapping_reminder2 = _get_message_from_file(
            "reminder_event_length_at_time2.json"
        )
        begin = nice_time(self.valid_event2.expiration)
        self.skill.handle_create_event(overlapping_reminder2)
        self.skill.ask_yesno.assert_called_with(
            "alert_overlapping_ask", {"event": "valid event 2",
                                      "begin": begin}
        )
        self.skill.confirm_alert = real_confirm

        self.reset_alert_manager()

    def test_handle_reschedule_alert(self):
        self.populate_alerts()

        real_rescheduler = self.skill.alert_manager.reschedule_alert
        self.skill.alert_manager.reschedule_alert = Mock(return_value=self.reschedule_event1)
        self.skill.ask_yesno.return_value = "yes"

        no_time = _get_message_from_file("reschedule_alert_no_time.json")
        no_alert = _get_message_from_file("reschedule_no_alert_stored.json")
        one_time = _get_message_from_file("reschedule_event.json")
        recurring = _get_message_from_file("reschedule_recurring_event.json")

        self.skill.handle_reschedule_alert(no_time)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with("error_no_time",
                                                   wait=True)
        self.skill.ask_yesno.assert_not_called()
        self.skill.alert_manager.reschedule_alert.assert_not_called()
        self.skill.speak_dialog.reset_mock()

        self.skill.handle_reschedule_alert(no_alert)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with("error_no_scheduled_kind",
                                                   {"kind": "event"},
                                                   wait=True)
        self.skill.ask_yesno.assert_not_called()
        self.skill.alert_manager.reschedule_alert.assert_not_called()
        self.skill.speak_dialog.reset_mock()

        self.skill.handle_reschedule_alert(recurring)
        self.skill.speak_dialog.assert_called_once()
        call_args = self.skill.speak_dialog.call_args
        self.assertEqual(call_args[0][0], "alert_rescheduled")
        self.skill.ask_yesno.assert_called_once()
        self.skill.alert_manager.reschedule_alert.assert_called_once()
        call_args = self.skill.alert_manager.reschedule_alert.call_args
        self.assertEqual(call_args[0][2], False)
        self.skill.speak_dialog.reset_mock()
        self.skill.ask_yesno.reset_mock()
        self.skill.alert_manager.reschedule_alert.reset_mock()

        self.skill.handle_reschedule_alert(one_time)
        self.skill.speak_dialog.assert_called_once()
        call_args = self.skill.speak_dialog.call_args
        self.assertEqual(call_args[0][0], "alert_rescheduled")
        self.skill.ask_yesno.assert_not_called()
        self.skill.alert_manager.reschedule_alert.assert_called_once()
        call_args = self.skill.alert_manager.reschedule_alert.call_args
        self.assertEqual(call_args[0][2], True)
        self.skill.speak_dialog.reset_mock()
        self.skill.ask_yesno.reset_mock()
        self.skill.alert_manager.reschedule_alert.reset_mock()

        self.skill.alert_manager.reschedule_alert = real_rescheduler
        
        self.reset_alert_manager()
    
    def test_handle_create_todo(self):
        self.populate_alerts()

        todo_message = _get_message_from_file("todo_list.json")
        todo_message_duplicate = _get_message_from_file("todo_list_duplicate.json")
        real_add_alert = self.skill.alert_manager.add_alert
        real_handle_add_subitem = self.skill.handle_add_subitem_to_todo
        self.skill.alert_manager.add_alert = Mock()
        self.skill.handle_add_subitem_to_todo = Mock()

        self.skill.handle_create_todo(todo_message)
        self.skill.alert_manager.add_alert.assert_called_once()
        self.assertEqual(
            self.skill.alert_manager.add_alert.call_args[0][0].alert_type,
            AlertType.TODO,
        )
        self.assertEqual(
            self.skill.alert_manager.add_alert.call_args[0][0].dav_type, DAVType.VTODO
        )
        self.skill.speak_dialog.assert_not_called()
        self.skill.handle_add_subitem_to_todo.assert_called_once()
        self.skill.alert_manager.add_alert.reset_mock()

        self.skill.handle_create_todo(todo_message_duplicate)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "list_todo_already_exist", {"name": "flowers"}, wait=True
        )
        self.skill.alert_manager.add_alert.assert_not_called()
        self.skill.speak_dialog.reset_mock()

        self.skill.alert_manager.add_alert = real_add_alert
        self.skill.handle_add_subitem_to_todo = real_handle_add_subitem

        self.reset_alert_manager()

    def test_handle_add_subitem_to_todo(self):
        self.populate_alerts()

        todo_message_add = _get_message_from_file("todo_list_add_subitems.json")
        self.skill._get_response_cascade.return_value=["strawberries", "blueberries"]
        # t = self.skill.handle_add_subitem_to_todo(todo_message_add)
        # while t.is_alive():
        #     time.sleep(1)
        self.skill.handle_add_subitem_to_todo(todo_message_add)
        self.assertEqual(self.skill.speak_dialog.call_count, 2)
        self.skill.speak_dialog.assert_called_with(
            "list_todo_subitems_added", {"num": "two"}
        )
        self.assertEqual(len(self.shopping_list.children), 4)
        _, _, ident_item1, ident_item2 = self.shopping_list.children
        item1 = self.skill.alert_manager.get_alert(ident_item1)
        item2 = self.skill.alert_manager.get_alert(ident_item2)
        self.assertEqual(self.shopping_list.ident, item1.related_to)
        self.assertEqual(self.shopping_list.ident, item2.related_to)

        self.reset_alert_manager()

    def test_handle_query_todo_list_names(self):
        self.populate_alerts()

        # list of todos (todos WITH subitems)
        message = Message("test", {})
        self.skill.handle_query_todo_list_names(message)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "list_todo_lists", {"num": "two", "lists": "shopping and dummy_list"}
        )
        self.skill.speak_dialog.reset_mock()

        # list of todos (todos WITHOUT subitems)
        self.skill.handle_query_todo_reminder_names(message)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "list_todo_reminder", {"reminders": "flowers"}
        )

        self.reset_alert_manager()

    def test_handle_todo_list_entries(self):
        self.populate_alerts()

        todo_list_entries = _get_message_from_file("todo_list_get_entries.json")
        self.skill.handle_todo_list_entries(todo_list_entries)
        self.skill.speak.assert_called_once()
        self.skill.speak.assert_called_with("mango and butter", wait=True)

        self.reset_alert_manager()

    def test_handle_delete_todo_list_entries(self):
        self.populate_alerts()

        # with list name
        list_delete_entry = _get_message_from_file("todo_entry_delete.json")
        self.skill._get_response_cascade.return_value=["butter"]
        self.skill.handle_delete_todo_list_entries(list_delete_entry)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with("list_todo_num_deleted", {"num": "one"})
        entries = self.skill.alert_manager.get_children(self.shopping_list.ident)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("butter", [entry.alert_name for entry in entries])
        self.skill.speak_dialog.reset_mock()

        # without list name (2 lists present)
        # NOTE: with only one list present, the list name is automatically selected 
        list_delete_entry = _get_message_from_file("todo_entry_delete_wo_listname.json")
        self.skill._get_response_cascade.return_value=["mango"]
        self.skill.ask_selection.return_value="shopping"
        self.skill.handle_delete_todo_list_entries(list_delete_entry)
        self.assertEqual(self.skill.speak_dialog.call_count, 2)
        self.skill.speak_dialog.assert_called_with("list_todo_num_deleted", {"num": "one"})
        entries = self.skill.alert_manager.get_children(self.shopping_list.ident)
        self.assertEqual(len(entries), 0)
        self.assertNotIn("mango", [entry.alert_name for entry in entries])
        self.skill.speak_dialog.reset_mock()

        self.populate_alerts([self.shopping_subitem1])
        # item not stored
        self.skill._get_response_cascade.return_value=["not there"]
        self.skill.handle_delete_todo_list_entries(list_delete_entry)
        self.assertEqual(self.skill.speak_dialog.call_count, 3)
        self.skill.speak_dialog.assert_called_with("list_todo_num_deleted", {"num": "zero"})
        self.skill.speak_dialog.reset_mock()

        # delete all items of a list
        todo_list_delete_all = _get_message_from_file("todo_entry_delete_all.json")
        shopping_items = len(self.skill.alert_manager.get_children(self.shopping_list.ident))
        assert shopping_items > 0
        self.skill.handle_delete_todo_list_entries(todo_list_delete_all)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with("list_todo_num_deleted",
                                                   {"num": pronounce_number(shopping_items)})

        self.reset_alert_manager()
    
    def test_handle_delete_todo_list(self):
        self.populate_alerts()

        list_delete = _get_message_from_file("todo_list_delete.json")
        self.skill.handle_delete_todo_list(list_delete)
        self.assertNotIn(self.shopping_list.ident, self.skill.alert_manager.pending_alerts)
        self.assertNotIn(self.shopping_subitem1.ident, self.skill.alert_manager.pending_alerts)
        self.assertNotIn(self.shopping_subitem2.ident, self.skill.alert_manager.pending_alerts)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with("list_deleted", {"name": "shopping"})
        self.reset_alert_manager()

        self.populate_alerts()

        list_delete_wo_name = _get_message_from_file("todo_list_delete_wo_name.json")
        self.skill.ask_selection.return_value="shopping"
        self.skill.handle_delete_todo_list(list_delete_wo_name)
        self.assertNotIn(self.shopping_list.ident, self.skill.alert_manager.pending_alerts)
        self.assertNotIn(self.shopping_subitem1.ident, self.skill.alert_manager.pending_alerts)
        self.assertNotIn(self.shopping_subitem2.ident, self.skill.alert_manager.pending_alerts)
        self.assertEqual(self.skill.speak_dialog.call_count, 2)
        self.skill.speak_dialog.assert_called_with("list_deleted", {"name": "shopping"})

    def test_handle_create_event(self):
        real_method = self.skill.handle_create_reminder
        create_reminder = Mock()
        self.skill.handle_create_reminder = create_reminder
        test_message = Message("test", {"data": True}, {"context": "test"})
        self.skill.handle_create_event(test_message)
        create_reminder.assert_called_once()
        create_reminder.assert_called_with(test_message)

        self.skill.handle_create_reminder = real_method

        self.reset_alert_manager()

    def test_handle_event_timeframe_check(self):
        self.populate_alerts()

        wd = ["monday", "tuesday", "wednesday",
              "thursday", "friday", "saturday", "sunday"]
        day = wd[self.valid_event.expiration.weekday()]
        check_message =_get_message_from_file("query_alerts_timeframe_event.json")

        # check in a time range (note: 1 minute gap 11:59-00:00)
        check_message.data["utterance"] = \
            f"are there any events between {day} 00:00 am and 11:59 pm"
        begin = nice_time(self.valid_event.expiration, use_ampm=True)

        self.skill.handle_event_timeframe_check(check_message)
        self.assertEqual(self.skill.speak_dialog.call_count, 2)
        call_args = self.skill.speak_dialog.call_args_list
        self.assertEqual(call_args[1][0][0], "list_alert_wo_duration")
        self.assertEqual(call_args[1][0][1]["begin"], begin)
        self.assertEqual(call_args[0][0][0], "list_alert_timeframe_intro")
        self.assertEqual(call_args[0][0][1]["num"], 1)
        self.assertEqual(call_args[0][0][1]["type"], "event")
        
        self.skill.speak_dialog.reset_mock()

        check_message.data.pop("and")  # crucial below, as this would indicate 2 datetimes
        del(check_message.data["__tags__"][2])

        # still a timeframe check as the end date gets set + timedelta(days=1)
        # in case of 00:00 hours/minutes
        # eg "today", "tomorrow", "3rd of october", "tuesday"
        check_message.data["utterance"] = \
            f"are there any events on {day}"

        self.skill.handle_event_timeframe_check(check_message)
        # same data as obove
        self.assertEqual(self.skill.speak_dialog.call_count, 2)
        
        self.skill.speak_dialog.reset_mock()

        # check at a specific time
        time_str = (self.valid_event.expiration + dt.timedelta(hours=1)).strftime("%I:%M %p")
        check_message.data["utterance"] = f"are there any events at {day} {time_str}"

        self.skill.handle_event_timeframe_check(check_message)
        # same data as obove
        self.assertEqual(self.skill.speak_dialog.call_count, 2)
        
        self.skill.speak_dialog.reset_mock()

        # specific time, no events to report
        time_str = (self.valid_event.expiration + dt.timedelta(hours=3)).strftime("%I:%M %p")
        check_message.data["utterance"] = f"are there any events at {day} {time_str}"

        self.skill.handle_event_timeframe_check(check_message)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with("list_alert_timeframe_none")
        
        self.skill.speak_dialog.reset_mock()

    	# no date -> handle_list_all_alerts (list all alerts of given type)
        check_message.data["utterance"] = f"are there any events stored?"

        self.skill.handle_event_timeframe_check(check_message)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with('list_alert_intro',
                                                   {'kind': 'event'},
                                                   wait=True)
        self.skill.speak.assert_called()
        
        self.reset_alert_manager()

    def test_handle_next_alert(self):
        self.populate_alerts()

        message_alarm = Message("test", {"alarm": "alarm"})
        message_timer = Message("test", {"timer": "timer"})
        message_reminder = Message("test", {"reminder": "reminder"})
        message_all = Message("test", {"alert": "alert"})

        # unnamed
        self.skill.handle_next_alert(message_alarm)
        self.skill.speak_dialog.assert_called_with(
            "next_alert",
            {
                "kind": "alarm",
                "name": "",
                "begin": nice_date_time(self.valid_alarm_1.expiration, use_ampm=True),
                "remaining": spoken_duration(self.valid_alarm_1.expiration,
                                             lang="en-us")
            },
            wait=True
        )

        self.skill.handle_next_alert(message_timer)
        self.skill.speak_dialog.assert_called_with(
            "next_alert_timer",
            {
                "kind": "timer",
                "name": "oven",
                "begin": nice_time(self.valid_timer.expiration, use_ampm=True),
                "remaining": spoken_duration(self.valid_timer.expiration,
                                                   lang="en-us")
            },
            wait=True
        )

        # named
        self.skill.handle_next_alert(message_reminder)
        self.skill.speak_dialog.assert_called_with(
            "next_alert",
            {
                "kind": "reminder",
                "name": self.valid_reminder.alert_name,
                "begin": nice_date_time(self.valid_reminder.expiration, use_ampm=True),
                "end": nice_date_time(self.valid_reminder.until, use_ampm=True),
                "remaining": spoken_duration(self.valid_reminder.expiration,
                                                   lang="en-us")
            },
            wait=True
        )

        # all types
        self.skill.handle_next_alert(message_all)
        self.skill.speak_dialog.assert_called_with(
            "next_alert_timer",
            {
                "kind": "timer",
                "name": "oven",
                "begin": nice_time(self.valid_timer.expiration, use_ampm=True),
                "remaining": spoken_duration(self.valid_timer.expiration,
                                                   lang="en-us")
            },
            wait=True
        )

    def test_handle_list_all_alerts(self):
        self.populate_alerts(exception=AlertType.TIMER)

        message_alarm = Message("test", {"alarm": "alarm"})
        message_timer = Message("test", {"timer": "timer"})
        message_reminder = Message("test", {"reminder": "reminder"})
        message_all = Message("test", {"alert": "alert"})

        # specific types
        self.skill.handle_list_all_alerts(message_alarm)
        self.skill.speak_dialog.assert_called()
        self.assertEqual(self.skill.speak_dialog.call_args[0][1]["kind"],
                         "alarm")
        self.assertEqual(self.skill.speak_dialog.call_count, 1)
        self.assertEqual(self.skill.speak.call_count, 3)
        self.skill.speak.reset_mock()
        self.skill.speak_dialog.reset_mock()

        self.skill.handle_list_all_alerts(message_reminder)
        self.assertEqual(self.skill.speak_dialog.call_args[0][1]["kind"],
                         "reminder")
        self.assertEqual(self.skill.speak_dialog.call_count, 1)
        self.assertEqual(self.skill.speak.call_count, 1)
        self.skill.speak.reset_mock()
        self.skill.speak_dialog.reset_mock()

        # specific type, nothing available
        self.skill.handle_list_all_alerts(message_timer)
        self.skill.speak_dialog.assert_called_with(
            "list_alert_none_upcoming", {"kind": "timer"}, wait=True
        )
        self.skill.speak.reset_mock()
        self.skill.speak_dialog.reset_mock()

        # every type
        self.skill.handle_list_all_alerts(message_all)
        calls = [call("list_alert_intro",{"kind": "event"}, wait=True),
                 call("list_alert_intro",{"kind": "reminder"}, wait=True),
                 call("list_alert_intro",{"kind": "alarm"}, wait=True)]
        self.skill.speak_dialog.assert_has_calls(calls, any_order=True)
        self.assertEqual(self.skill.speak_dialog.call_count, 3)
        self.assertEqual(self.skill.speak.call_count, 8)

        self.reset_alert_manager()

    def test_handle_timer_status(self):

        real_timer_status = self.skill._display_timers
        self.skill._display_timers = Mock()

        now_time = dt.datetime.now(get_default_tz()).replace(microsecond=0)
        test_timer = Alert.create(
            expiration=now_time + dt.timedelta(minutes=5),
            alert_name="5 minute timer",
            alert_type=AlertType.TIMER
        )
        long_timer = Alert.create(
            expiration=now_time + dt.timedelta(minutes=30),
            alert_name="oven",
            alert_type=AlertType.TIMER
        )

        # No active timers
        self.skill.handle_timer_status(Message("test", {"timer_time_remaining": ""}))
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "timer_status_none_active", wait=True
        )
        self.skill.speak_dialog.reset_mock()

        # Single active timer not specifically requested
        self.skill.alert_manager.add_alert(long_timer)
        self.skill.handle_timer_status(Message("test", {"timer_time_remaining": ""}))
        self.skill.speak_dialog.assert_called_once()
        call_args = self.skill.speak_dialog.call_args
        self.assertEqual(call_args[0][0], "timer_status")
        self.assertEqual(call_args[0][1]["name"], long_timer.alert_name)
        self.assertIsNotNone(call_args[0][1]["remaining"])
        self.assertTrue(call_args[1]["wait"])
        self.skill._display_timers.assert_called_with([long_timer])
        self.skill.speak_dialog.reset_mock()

        # Multiple active timers not specifically requested
        self.skill.alert_manager.add_alert(test_timer)
        self.skill.handle_timer_status(Message("test", {"timer_time_remaining": ""}))
        self.assertEqual(self.skill.speak_dialog.call_count, 2)
        call_args = self.skill.speak_dialog.call_args
        self.assertEqual(call_args[0][0], "timer_status")

        # Multiple active timers, one specifically requested
        request = _get_message_from_file("timer_request_time_left.json")
        self.skill.handle_timer_status(request)
        call_args = self.skill.speak_dialog.call_args
        self.assertEqual(call_args[0][0], "timer_status")
        self.assertEqual(call_args[0][1]["name"], long_timer.alert_name)
        self.assertIsNotNone(call_args[0][1]["remaining"])
        self.assertTrue(call_args[1]["wait"])
        self.skill._display_timers.assert_called_with([long_timer])

        self.skill._display_timers = real_timer_status

        self.reset_alert_manager()

    def test_handle_missed_alerts(self):

        test_message = Message(
            "test", {}
        )

        # nothing missed
        self.skill.handle_missed_alerts(test_message)
        first_call = self.skill.speak_dialog.call_args_list[0]
        self.assertEqual(first_call, call("list_alert_none_missed", wait=True))

        self.skill.speak_dialog.reset_mock()

        # 1 alarm missed
        self.skill.alert_manager._missed_alerts = {self.past_alarm.ident: self.past_alarm}
        self.skill.handle_missed_alerts(test_message)
        self.skill.speak_dialog.call_count = 2
        first_call = self.skill.speak_dialog.call_args_list[0]
        second_call = self.skill.speak_dialog.call_args_list[1]
        self.assertEqual(first_call, call('list_alert_missed_intro', wait=True))
        self.assertEqual(second_call[0][0], 'list_alert_missed')

        self.reset_alert_manager()

    def test_handle_cancel_alert(self):
        default_tz = get_default_tz()
        now_time = dt.datetime.now(default_tz).replace(microsecond=0)
        alarm_1_time = now_time + dt.timedelta(days=1)
        alarm_2_time = alarm_1_time + dt.timedelta(hours=1)
        alarm_3_time = now_time.replace(hour=9, minute=30, second=0) + dt.timedelta(
            days=1
        )
        reminder_time = now_time + dt.timedelta(days=2)
        timer_1_time = now_time + dt.timedelta(minutes=5)
        timer_2_time = now_time + dt.timedelta(minutes=10)

        # Define alerts
        tomorrow_alarm = Alert.create(
            expiration=alarm_1_time,
            alert_type=AlertType.ALARM
        )
        later_alarm = Alert.create(
            expiration=alarm_2_time,
            alert_type=AlertType.ALARM
        )
        morning_alarm = Alert.create(
            expiration=alarm_3_time,
            alert_name="9:30 AM alarm",
            alert_type=AlertType.ALARM
        )
        trash_reminder = Alert.create(
            expiration=reminder_time,
            alert_name="take out garbage",
            alert_type=AlertType.REMINDER
        )
        pasta_timer = Alert.create(
            expiration=timer_1_time,
            alert_name="pasta",
            alert_type=AlertType.TIMER
        )
        unnamed_timer = Alert.create(
            expiration=timer_1_time,
            alert_type=AlertType.TIMER
        )
        oven_timer = Alert.create(
            expiration=timer_2_time,
            alert_name="cherry pie",
            alert_type=AlertType.TIMER
        )

        alerts = [tomorrow_alarm,
                  later_alarm,
                  morning_alarm,
                  trash_reminder,
                  pasta_timer,
                  oven_timer,
                  unnamed_timer]
        
        today_alerts = [a for a in alerts if
                        a.expiration.date() == now_time.date()]
        not_today_alerts = [a for a in alerts if a not in today_alerts]

        self.populate_alerts(alerts)

        # Cancel only alert of type
        message = Message(
            "test",
            {"cancel": "cancel", "reminder": "reminder"}
        )
        self.skill.ask_selection.return_value = trash_reminder.alert_name
        self.skill.handle_cancel_alert(message)
        self.assertNotIn(
            trash_reminder.ident, self.skill.alert_manager.pending_alerts.keys()
        )
        self.skill.speak_dialog.assert_called_with(
            "confirm_cancel_alert",
            {"kind": "reminder", "name": trash_reminder.alert_name},
            wait=True,
        )
        self.skill.speak_dialog.reset_mock()

        # Cancel no alerts of requested type
        self.skill.handle_cancel_alert(message)
        self.skill.speak_dialog.assert_called_with(
            "error_no_scheduled_kind", {"kind": "reminder"}, wait=True
        )
        self.skill.speak_dialog.reset_mock()

        # Cancel no match
        message = Message(
            "test",
            {
                "cancel": "cancel",
                "timer": "timer",
                "utterance": "cancel my test timer",
                "__tags__": [
                    {
                        "match": "cancel",
                        "key": "cancel",
                        "start_token": 0,
                        "end_token": 0,
                    },
                    {
                        "match": "timer",
                        "key": "timer",
                        "start_token": 3,
                        "end_token": 3,
                    },
                ],
            }
        )
        pending = self.skill.alert_manager.pending_alerts.keys()
        self.skill.handle_cancel_alert(message)
        self.skill.speak_dialog.assert_called_with(
            "error_nothing_to_cancel", wait=True
        )
        self.assertEqual(pending, self.skill.alert_manager.pending_alerts.keys())
        self.skill.speak_dialog.reset_mock()

        # Cancel match name  pasta timer
        message = Message(
            "test",
            {
                "cancel": "cancel",
                "timer": "timer",
                "utterance": "cancel my pasta timer",
                "__tags__": [
                    {
                        "match": "cancel",
                        "key": "cancel",
                        "start_token": 0,
                        "end_token": 0,
                    },
                    {
                        "match": "timer",
                        "key": "timer",
                        "start_token": 3,
                        "end_token": 3,
                    },
                ],
            }
        )
        self.assertIn(pasta_timer.ident, self.skill.alert_manager.pending_alerts.keys())
        self.skill.handle_cancel_alert(message)
        self.assertNotIn(
            pasta_timer.ident, self.skill.alert_manager.pending_alerts.keys()
        )
        self.skill.speak_dialog.assert_called_with(
            "confirm_cancel_alert",
            {"kind": "timer", "name": pasta_timer.alert_name},
            wait=True,
        )
        self.skill.speak_dialog.reset_mock()

        # Cancel match time 9:30 AM alarm
        message = Message(
            "test",
            {
                "cancel": "cancel",
                "alarm": "alarm",
                "utterance": "cancel my 9:30 AM alarm",
                "__tags__": [
                    {
                        "match": "cancel",
                        "key": "cancel",
                        "start_token": 0,
                        "end_token": 0,
                    },
                    {
                        "match": "alarm",
                        "key": "alarm",
                        "start_token": 4,
                        "end_token": 4,
                    },
                ],
            }
        )
        self.assertIn(
            morning_alarm.ident, self.skill.alert_manager.pending_alerts.keys()
        )
        self.skill.handle_cancel_alert(message)
        self.assertNotIn(
            morning_alarm.ident, self.skill.alert_manager.pending_alerts.keys()
        )
        # note: "9:30 AM alarm" (default name) -> "9:30 AM"
        # for dialog purposes 
        self.skill.speak_dialog.assert_called_with(
            "confirm_cancel_alert",
            {"kind": "alarm", "name": "9:30 AM"},
            wait=True,
        )
        self.skill.speak_dialog.reset_mock()

        # Cancel partial name oven (cherry pie)
        message = Message(
            "test",
            {
                "cancel": "cancel",
                "timer": "timer",
                "utterance": "cancel my pie timer",
                "__tags__": [
                    {
                        "match": "cancel",
                        "key": "cancel",
                        "start_token": 0,
                        "end_token": 0,
                    },
                    {
                        "match": "timer",
                        "key": "timer",
                        "start_token": 3,
                        "end_token": 3,
                    },
                ],
            }
        )
        self.assertIn(oven_timer.ident, self.skill.alert_manager.pending_alerts.keys())
        self.skill.handle_cancel_alert(message)
        self.assertNotIn(
            oven_timer.ident, self.skill.alert_manager.pending_alerts.keys()
        )
        self.skill.speak_dialog.assert_called_with(
            "confirm_cancel_alert",
            {"kind": "timer", "name": oven_timer.alert_name},
            wait=True,
        )
        self.skill.speak_dialog.reset_mock()

        # Cancel all valid
        message = Message(
            "test",
            {"cancel": "cancel", "alert": "alert", "stored": "all"}
        )
        self.skill.handle_cancel_alert(message)
        self.skill.speak_dialog.assert_called_with(
            "confirm_cancel_all", {"kind": "alert"}, wait=True
        )
        self.assertEqual(
            self.skill.alert_manager.get_alerts(),
            {"missed": list(), "active": list(), "pending": list()},
        )
        self.skill.speak_dialog.reset_mock()

        # Cancel all nothing to cancel
        self.skill.handle_cancel_alert(message)
        self.skill.speak_dialog.assert_called_with(
            "error_nothing_to_cancel", wait=True
        )
        self.skill.speak_dialog.reset_mock()

        # cancel timeframe
        self.populate_alerts(alerts)
        message = Message(
            "test",
            {
                "cancel": "cancel",
                "alert": "alerts",
                "utterance": "cancel alerts from today",
                "__tags__": [
                    {
                        "match": "cancel",
                        "key": "cancel",
                        "start_token": 0,
                        "end_token": 0,
                    },
                    {
                        "match": "alerts",
                        "key": "alert",
                        "start_token": 1,
                        "end_token": 1,
                    },
                ],
            }
        )
        self.skill.handle_cancel_alert(message)
        self.skill.speak_dialog.assert_called_with(
            "confirm_cancel_timeframe", {'kind': 'alert'} , wait=True
        )
        self.assertEqual(len(self.skill.alert_manager.pending_alerts),
                         len(not_today_alerts))


    def test_confirm_alert(self):
        default_tz = get_default_tz()
        creation_time = dt.datetime.now(default_tz).replace(microsecond=0)
        use_24hour = self.skill.use_24hour
        message = Message("", data={"lang": "en-us"})

        real_display_timer = self.skill._display_timers
        real_display_alarm = self.skill._display_alarms
        self.skill._display_timers = Mock()
        self.skill._display_alarms = Mock()

        # Timer
        timer1 = Alert.create(
            expiration=creation_time + dt.timedelta(minutes=20),
            alert_type=AlertType.TIMER,
            context={"created": creation_time.timestamp()},
        )
        self.skill.confirm_alert(timer1, message)
        self.skill._display_timers.assert_called_once()
        self.skill._display_alarms.assert_not_called()
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "confirm_timer_started", {"remaining": "twenty minutes"}, wait=True
        )
        self.skill.alert_manager.rm_alert(timer1.ident)
        self.skill.speak_dialog.reset_mock()
        self.skill._display_timers.reset_mock()

        # Timer Timeresolution.MINUTES
        timer2 = Alert.create(
            expiration=creation_time + dt.timedelta(hours=2, minutes=30, seconds=20),
            alert_type=AlertType.TIMER,
            context={"created": creation_time.timestamp()},
        )
        self.skill.confirm_alert(timer2, message)
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "confirm_timer_started",
            {"remaining": "two hours thirty minutes"},
            wait=True,
        )
        self.skill.alert_manager.rm_alert(timer2.ident)
        self.skill._display_timers.reset_mock()
        self.skill.speak_dialog.reset_mock()

        # Alarm single
        alarm_single = Alert.create(
            expiration=creation_time + dt.timedelta(hours=1),
            alert_type=AlertType.ALARM,
            context={"created": creation_time.timestamp()},
        )
        time_ = nice_time(
            alarm_single.expiration,
            "en-us",
            use_24hour=use_24hour,
            use_ampm=not use_24hour,
        )
        self.skill.confirm_alert(alarm_single, message)
        self.skill._display_timers.assert_not_called()
        self.skill._display_alarms.assert_called_once()
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "confirm_alert_set",
            {"kind": "alarm", "begin": time_, "remaining": "one hour"},
            wait=True,
        )
        self.skill.alert_manager.rm_alert(alarm_single.ident)
        self.skill.speak_dialog.reset_mock()
        self.skill._display_alarms.reset_mock()

        # Alarm recurring weekdays
        alarm_rec_wd = Alert.create(
            expiration=creation_time + dt.timedelta(hours=1),
            alert_type=AlertType.ALARM,
            repeat_days=[Weekdays(i) for i in range(0, 5)],
            context={"created": creation_time.timestamp()},
        )
        repeat_ = "Monday through Friday"
        self.skill.confirm_alert(alarm_rec_wd, message)
        self.skill._display_timers.assert_not_called()
        self.skill._display_alarms.assert_called_once()
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "confirm_alert_recurring",
            {"kind": "alarm", "begin": time_, "repeat": repeat_},
            wait=True,
        )
        self.skill.alert_manager.rm_alert(alarm_rec_wd.ident)
        self.skill.speak_dialog.reset_mock()
        self.skill._display_alarms.reset_mock()

        # Alarm recurring every day
        alarm_rec_ed = Alert.create(
            expiration=creation_time + dt.timedelta(hours=1),
            alert_type=AlertType.ALARM,
            repeat_days=[Weekdays(i) for i in range(0, 7)],
            context={"created": creation_time.timestamp()},
        )
        self.skill.confirm_alert(alarm_rec_ed, message)
        self.skill._display_timers.assert_not_called()
        self.skill._display_alarms.assert_called_once()
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "confirm_alert_recurring",
            {"kind": "alarm", "begin": time_, "repeat": "day"},
            wait=True,
        )
        self.skill.alert_manager.rm_alert(alarm_rec_ed.ident)
        self.skill.speak_dialog.reset_mock()
        self.skill._display_alarms.reset_mock()

        # Alarm recurring repeat frequency
        alarm_rec_rf = Alert.create(
            expiration=creation_time + dt.timedelta(hours=1),
            alert_type=AlertType.ALARM,
            repeat_frequency=dt.timedelta(hours=2),
            context={"created": creation_time.timestamp()},
        )
        self.skill.confirm_alert(alarm_rec_rf, message)
        self.skill._display_timers.assert_not_called()
        self.skill._display_alarms.assert_called_once()
        self.skill.speak_dialog.assert_called_once()
        self.skill.speak_dialog.assert_called_with(
            "confirm_alert_recurring",
            {"kind": "alarm", "begin": time_, "repeat": "two hours"},
            wait=True,
        )
        self.skill.alert_manager.rm_alert(alarm_rec_rf.ident)
        self.skill.speak_dialog.reset_mock()
        self.skill._display_alarms.reset_mock()

        self.skill._display_timers = real_display_timer
        self.skill._display_alarms = real_display_alarm

        self.reset_alert_manager()

    def test_alert_prenotification(self):
        now = sleep_until_full_second()

        # real_preference = self.skill.preference_skill
        # self.skill.preference_skill = Mock(return_value={"timeout_min": 0.01})
        self.skill.settings["timeout_min"] = 0.01
        prenotification_alert = Alert.create(
            expiration=now + dt.timedelta(hours=1),
            prenotification=0,
            alert_type=AlertType.EVENT,
            alert_name="prenotification_test",
            context={"alert_reason": "prenotification"},
        )
        self.skill.alert_manager.add_alert(prenotification_alert)
        message = Message.deserialize(prenotification_alert.serialize)
        self.skill.alert_manager._handle_alert_expiration(message)
        self.assertIn(prenotification_alert.ident,
                      self.skill.alert_manager._missed_alerts)
        self.assertIn(prenotification_alert.ident,
                      self.skill.alert_manager._pending_alerts)
        self.skill.speak_dialog.assert_called_once()
        arg = self.skill.speak_dialog.call_args[0][1]
        self.assertIn(
            arg["time_until"], ["one hour", "fifty nine minutes fifty nine seconds"]
        )
        
        self.skill.alert_manager.rm_alert(prenotification_alert.ident)
        self.assertNotIn(prenotification_alert.ident,
                      self.skill.alert_manager._missed_alerts)
        self.assertIn(prenotification_alert.ident,
                      self.skill.alert_manager._pending_alerts)
        
        self.reset_alert_manager()
        self.skill.settings["timeout_min"] = 2        

    def test_alert_expired(self):
        # TODO
        pass

    def test_play_notify_expired(self):
        # TODO
        pass

    def test_speak_notify_expired(self):
        # TODO
        pass

    def test_gui_timer_status(self):
        # TODO
        pass

    def test_gui_notify_expired(self):
        # TODO
        pass

    def test_resolve_requested_alert(self):
        # TODO
        pass

    def test_get_events(self):
        # TODO
        pass

    def test_get_requested_alert_name_and_time(self):
        # TODO
        pass

    def test_get_alert_type_from_intent(self):
        # TODO
        pass

    @patch("skill_alerts.util.locale.translate")
    @patch("skill_alerts.util.locale.spoken_alert_type")
    def test_get_alert_dialog_data(self, mock_spoken_type, mock_translate):
        mock_translate.return_value="translated"
        mock_spoken_type.return_value="translated"

        now_time = dt.datetime.now(dt.timezone.utc)
        # Alert for tomorrow at 9 AM
        tomorrow_alert_time = (now_time + dt.timedelta(days=2)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        # Alert for later today
        today_alert_time = now_time + dt.timedelta(minutes=1)
        # TODO: Above will fail if run at 11:59PM; consider better mocking

        # Event later today | test nice time | test event duration
        today_alert = Alert.create(
            expiration=today_alert_time,
            until=now_time + dt.timedelta(hours=1),
            alert_name="appointment",
            alert_type=AlertType.ALARM,
        )
        dialog = get_alert_dialog_data(today_alert, "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "appointment",
                "kind": "translated",
                "begin": nice_time(
                    today_alert.expiration, use_24hour=False, use_ampm=True
                ),
                "end": nice_time(
                    today_alert.until, use_24hour=False, use_ampm=True
                ),
                "remaining": "one minute",
            },
        )

        # One time alarm not today | test nice date time
        one_time = Alert.create(
            expiration=tomorrow_alert_time,
            alert_name="wakeup",
            alert_type=AlertType.ALARM,
        )
        dialog = get_alert_dialog_data(one_time, "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "wakeup",
                "kind": "translated",
                "begin": nice_date_time(
                    one_time.expiration, use_24hour=False, use_ampm=True
                ),
                "remaining": spoken_duration(one_time.expiration,
                                                   lang="en-us")
            },
        )

        # Weekend alarm | test repeat
        # repeat alerts are spoken without date info
        weekend = Alert.create(
            expiration=tomorrow_alert_time,
            alert_name="weekend routine",
            alert_type=AlertType.ALARM,
            repeat_days={Weekdays.SUN, Weekdays.SAT},
        )
        dialog = get_alert_dialog_data(weekend, "en-us")
        mock_translate.assert_called_with("weekend", "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "weekend routine",
                "kind": "translated",
                "repeat": "translated",
                "begin": nice_time(
                    weekend.expiration, use_24hour=False, use_ampm=True
                ),
                "remaining": spoken_duration(weekend.expiration,
                                                   lang="en-us")
            },
        )

        # Weekday alert | test repeat
        # repeat alerts are spoken without date info
        weekday = Alert.create(
            expiration=tomorrow_alert_time,
            alert_name="weekday routine",
            alert_type=AlertType.REMINDER,
            repeat_days={
                Weekdays.MON,
                Weekdays.TUE,
                Weekdays.WED,
                Weekdays.THU,
                Weekdays.FRI,
            },
        )
        dialog = get_alert_dialog_data(weekday, "en-us")
        mock_translate.assert_called_with("weekday", "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "weekday routine",
                "kind": "translated",
                "repeat": "translated",
                "begin": nice_time(
                    weekday.expiration, use_24hour=False, use_ampm=True
                ),
                "remaining": spoken_duration(weekday.expiration,
                                                   lang="en-us")
            },
        )

        # Daily alert | test repeat
        # repeat alerts are spoken without date info
        daily = Alert.create(
            expiration=tomorrow_alert_time,
            alert_name="daily routine",
            alert_type=AlertType.REMINDER,
            repeat_days={
                Weekdays.MON,
                Weekdays.TUE,
                Weekdays.WED,
                Weekdays.THU,
                Weekdays.FRI,
                Weekdays.SAT,
                Weekdays.SUN,
            },
        )
        dialog = get_alert_dialog_data(daily, "en-us")
        mock_translate.assert_called_with("day", "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "daily routine",
                "repeat": "translated",
                "kind": "translated",
                "begin": nice_time(
                    daily.expiration, use_24hour=False, use_ampm=True
                ),
                "remaining": spoken_duration(daily.expiration,
                                                   lang="en-us")
            },
        )

        # Weekly Alert | test repeat
        # repeat alerts are spoken without date info
        weekly = Alert.create(
            expiration=tomorrow_alert_time,
            alert_name="weekly routine",
            alert_type=AlertType.REMINDER,
            repeat_days={Weekdays.MON},
        )
        dialog = get_alert_dialog_data(weekly, "en-us")
        mock_translate.assert_called_with("monday", "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "weekly routine",
                "repeat": "translated",
                "kind": "translated",
                "begin": nice_time(
                    weekly.expiration, use_24hour=False, use_ampm=True
                ),
                "remaining": spoken_duration(daily.expiration,
                                                   lang="en-us")
            },
        )

        # 8 hour reminder | test repeat frequency
        eight_hour = Alert.create(
            expiration=tomorrow_alert_time,
            alert_name="take pill",
            alert_type=AlertType.REMINDER,
            repeat_frequency=dt.timedelta(hours=8),
        )
        dialog = get_alert_dialog_data(eight_hour, "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "take pill",
                "kind": "translated",
                "repeat": nice_duration(dt.timedelta(hours=8).total_seconds()),
                "begin": nice_time(
                    eight_hour.expiration, use_24hour=False, use_ampm=True
                ),
                "remaining": spoken_duration(daily.expiration,
                                                   lang="en-us")
            },
        )

        mock_spoken_type.return_value = "timer"

        # 2 minute timer | test default name
        # ie name created with util.parse_utils.get_default_alert_name
        # name gets replaced by empty string
        two_minute = Alert.create(
            expiration=now_time+dt.timedelta(minutes=2),
            alert_name="2 minute timer",
            alert_type=AlertType.TIMER
        )
        dialog = get_alert_dialog_data(two_minute, "en-us")
        self.assertEqual(
            dialog,
            {
                "name": "",
                "kind": "timer",
                "begin": nice_time(
                    two_minute.expiration, use_24hour=False, use_ampm=True
                ),
                "remaining": "two minutes"
            },
        )

    def test_dismiss_alert(self):
        real_drop_dav = self.skill.alert_manager.drop_dav_item
        self.skill.alert_manager.drop_dav_item = Mock()
        # Setup alert_manager with active alerts
        alert_manager = self.skill.alert_manager
        now_time = dt.datetime.now(dt.timezone.utc)
        alarm_time = now_time + dt.timedelta(seconds=1)
        timer_time = now_time + dt.timedelta(seconds=2)
        reminder_time = now_time + dt.timedelta(seconds=3)
        alarm = Alert.create(expiration=alarm_time, alert_type=AlertType.ALARM)
        alarm_id = alarm.ident
        timer = Alert.create(expiration=timer_time, alert_type=AlertType.TIMER)
        timer_id = timer.ident
        reminder = Alert.create(expiration=reminder_time, alert_type=AlertType.REMINDER)
        reminder_id = reminder.ident
        reminder.synchronized = True
        #time.sleep(2)

        update_msg: Message = None

        def _handle_message(msg):
            nonlocal update_msg
            update_msg = msg

        self.skill.bus.on("ovos.widgets.update", _handle_message)

        alert_manager._active_alerts = {timer_id: timer,
                                        alarm_id: alarm,
                                        reminder_id: reminder}
        alert_manager._synchron_ids = {reminder.ident}

        self.skill._dismiss_alert(alarm.ident)
        self.skill.speak_dialog.assert_not_called()
        self.assertIsInstance(update_msg, Message)
        self.assertEqual(update_msg.msg_type, "ovos.widgets.update")
        self.assertEqual(
            update_msg.data,
            {"type": "alarm",
             "data": {"count": 0, "action": "ovos.gui.show.pending.alarms"}},
        )

        # dismiss timer with confirmation
        self.skill._dismiss_alert(timer.ident, speak=True)
        self.skill.speak_dialog.assert_called_once_with(
            "confirm_dismiss_alert", {"kind": "timer"}
        )
        self.assertEqual(
            update_msg.data,
            {"type": "timer",
             "data": {"count": 0, "action": "ovos.gui.show.pending.timers"}},
        )

        # dismiss reminder, drop dav content
        self.skill._dismiss_alert(reminder.ident, drop_dav=True)
        alert_manager.drop_dav_item.assert_called_once()

        self.assertEqual(alert_manager._active_alerts, {})
        self.assertEqual(alert_manager._synchron_ids, set())

        self.skill.alert_manager.drop_dav_item = real_drop_dav

        self.reset_alert_manager()

    def test_get_spoken_alert_type(self):
        # TODO
        pass

    def test_get_spoken_weekday(self):
        # TODO
        pass


@unittest.skip('Work in progress')
class TestAlert(unittest.TestCase):
    def test_alert_create(self):
        now_time_valid = dt.datetime.now(dt.timezone.utc)
        now_time_invalid = dt.datetime.now()
        until_valid = now_time_valid + dt.timedelta(days=14)
        until_invalid = now_time_invalid + dt.timedelta(days=14)

        with self.assertRaises(ValueError):
            Alert.create(expiration=now_time_invalid)

        with self.assertRaises(ValueError):
            Alert.create(expiration=now_time_valid, until=until_invalid)

        test_alert = Alert.create(
            expiration=now_time_valid + dt.timedelta(hours=1),
            alert_name="test alert name",
            alert_type=AlertType.ALARM,
            priority=AlertPriority.HIGHEST.value,
            repeat_frequency=3600,
            until=until_valid,
            audio_file="audio_file",
            context={"testing": True, "created": now_time_valid.timestamp()},
        )

        # Test alert dump/reload
        dumped_alert = test_alert.data
        self.assertIsInstance(dumped_alert, dict)
        self.assertEqual(dumped_alert, Alert.from_dict(dumped_alert).data)

        # Test alert serialize/deserialize
        serial_alert = test_alert.serialize
        self.assertIsInstance(serial_alert, str)
        self.assertEqual(serial_alert, Alert.deserialize(serial_alert).serialize)

    def test_alert_properties(self):
        now_time_valid = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        until_valid = now_time_valid + dt.timedelta(days=14)

        future_alert_no_repeat = Alert.create(
            expiration=now_time_valid + dt.timedelta(hours=1),
            prenotification=-1800,
            alert_name="test alert name",
            alert_type=AlertType.ALARM,
            priority=AlertPriority.HIGHEST.value,
            repeat_frequency=3600,
            until=until_valid,
            audio_file="audio_file",
            context={"testing": True,
                     "created": now_time_valid.timestamp(),
                     "ident": "ident"},
        )

        # Test alert properties
        self.assertEqual(future_alert_no_repeat.created, now_time_valid)
        self.assertEqual(future_alert_no_repeat.alert_type, AlertType.ALARM)
        self.assertEqual(future_alert_no_repeat.priority, 10)
        self.assertEqual(future_alert_no_repeat.until, until_valid)
        self.assertIsNone(future_alert_no_repeat.repeat_days)
        self.assertEqual(
            future_alert_no_repeat.repeat_frequency, dt.timedelta(seconds=3600)
        )
        self.assertEqual(
            future_alert_no_repeat.context,
            {"testing": True, "created": now_time_valid.timestamp(), "ident": "ident"},
        )
        self.assertEqual(future_alert_no_repeat.alert_name, "test alert name")
        self.assertEqual(future_alert_no_repeat.audio_file, "audio_file")
        self.assertFalse(future_alert_no_repeat.is_expired)
        self.assertEqual(
            future_alert_no_repeat.expiration,
            future_alert_no_repeat.created + dt.timedelta(hours=1),
        )
        self.assertEqual(
            future_alert_no_repeat.prenotification,
            future_alert_no_repeat.created + dt.timedelta(minutes=30),
        )
        self.assertIsInstance(future_alert_no_repeat.time_to_expiration, dt.timedelta)

        expired_alert_no_repeat = Alert.create(
            expiration=now_time_valid - dt.timedelta(hours=1),
            alert_name="expired alert name",
            alert_type=AlertType.REMINDER,
            priority=AlertPriority.AVERAGE.value,
            audio_file="audio_file",
            context={"testing": True,
                     "created": now_time_valid.timestamp(),
                     "ident": "ident"},
        )
        # Test alert properties
        self.assertEqual(expired_alert_no_repeat.created, now_time_valid)
        self.assertEqual(expired_alert_no_repeat.alert_type, AlertType.REMINDER)
        self.assertEqual(expired_alert_no_repeat.dav_type, DAVType.VEVENT)
        self.assertEqual(expired_alert_no_repeat.priority, 5)
        self.assertIsNone(expired_alert_no_repeat.until)
        self.assertIsNone(expired_alert_no_repeat.repeat_days)
        self.assertIsNone(expired_alert_no_repeat.repeat_frequency)
        self.assertEqual(
            expired_alert_no_repeat.context,
            {"testing": True, "created": now_time_valid.timestamp(),"ident": "ident"},
        )
        self.assertEqual(expired_alert_no_repeat.alert_name, "expired alert name")
        self.assertEqual(expired_alert_no_repeat.audio_file, "audio_file")
        self.assertTrue(expired_alert_no_repeat.is_expired)
        self.assertIsNone(expired_alert_no_repeat.expiration)
        self.assertIsNone(expired_alert_no_repeat.prenotification)
        self.assertLessEqual(
            expired_alert_no_repeat.time_to_expiration.total_seconds(), 0
        )

        related_todo = Alert.create(
            alert_name="todo reminder",
            alert_type=AlertType.TODO,
            priority=AlertPriority.AVERAGE.value,
            audio_file="audio_file",
            context={"related_to": "uuid",
                     "created": now_time_valid.timestamp(),
                     "ident": "ident"},
        )
        # Test alert properties
        self.assertEqual(related_todo.alert_type, AlertType.TODO)
        self.assertEqual(related_todo.dav_type, DAVType.VTODO)
        self.assertEqual(related_todo.priority, 5)
        self.assertIsNone(related_todo.until)
        self.assertIsNone(related_todo.repeat_days)
        self.assertIsNone(related_todo.repeat_frequency)
        self.assertEqual(
            related_todo.context,
            {"related_to": "uuid",
             "created": now_time_valid.timestamp(),
             "ident": "ident"},
        )
        self.assertEqual(related_todo.alert_name, "todo reminder")
        self.assertIsNone(related_todo.expiration)
        self.assertLessEqual(
            expired_alert_no_repeat.time_to_expiration.total_seconds(), 0
        )

        expired_alert_expired_repeat = Alert.create(
            expiration=now_time_valid - dt.timedelta(hours=6),
            alert_name="expired alert name",
            repeat_frequency=dt.timedelta(hours=1),
            until=now_time_valid - dt.timedelta(hours=1),
            context={"testing": True,
                     "created": now_time_valid.timestamp(),
                     "ident": "ident"},
        )
        # Test alert properties
        self.assertEqual(
            expired_alert_expired_repeat.repeat_frequency, dt.timedelta(hours=1)
        )
        self.assertIsInstance(expired_alert_expired_repeat.until, dt.datetime)
        self.assertIsNone(expired_alert_expired_repeat.repeat_days)
        self.assertEqual(
            expired_alert_expired_repeat.context,
            {"testing": True, "created": now_time_valid.timestamp(), "ident": "ident"},
        )
        self.assertEqual(expired_alert_expired_repeat.alert_name, "expired alert name")
        self.assertTrue(expired_alert_expired_repeat.is_expired)
        self.assertIsNone(expired_alert_expired_repeat.expiration)
        self.assertLessEqual(
            expired_alert_expired_repeat.time_to_expiration.total_seconds(), 0
        )

        alert_time = now_time_valid - dt.timedelta(hours=1)
        expired_alert_weekday_repeat = Alert.create(
            expiration=alert_time,
            alert_name="expired weekly alert name",
            repeat_days={Weekdays(alert_time.weekday())},
            context={"testing": True,
                     "created": now_time_valid.timestamp(),
                     "ident": "ident"},
        )
        # Test alert properties
        self.assertIsNone(expired_alert_weekday_repeat.until)
        self.assertEqual(
            expired_alert_weekday_repeat.repeat_days, {Weekdays(alert_time.weekday())}
        )
        self.assertIsNone(expired_alert_weekday_repeat.repeat_frequency)
        self.assertEqual(
            expired_alert_weekday_repeat.context,
            {"testing": True, "created": now_time_valid.timestamp(), "ident": "ident"},
        )
        self.assertEqual(
            expired_alert_weekday_repeat.alert_name, "expired weekly alert name"
        )
        self.assertTrue(expired_alert_weekday_repeat.is_expired)
        self.assertIsInstance(expired_alert_weekday_repeat.expiration, dt.datetime)
        self.assertFalse(expired_alert_weekday_repeat.is_expired)
        self.assertEqual(
            expired_alert_weekday_repeat.expiration,
            alert_time + dt.timedelta(weeks=1),
        )

        # Comparison is rounded to account for processing time
        self.assertAlmostEqual(
            expired_alert_weekday_repeat.time_to_expiration.total_seconds(),
            dt.timedelta(weeks=1, hours=-1).total_seconds(),
            delta=5,
        )

    def test_alert_add_context(self):
        now = dt.datetime.now(dt.timezone.utc)
        alert_time = now + dt.timedelta(hours=1)
        alert = Alert.create(
            expiration=alert_time,
            alert_name="test alert context",
            context={"testing": True},
        )
        alert_id = alert.ident
        # timestamp and ident added on creation
        self.assertEqual(len(alert.context), 3)
        self.assertIn("ident", alert.context)
        self.assertEqual(alert.context["ident"], alert_id)
        self.assertAlmostEqual(alert.context["created"], now.timestamp(), delta=0.1)

        timestamp = alert.context["created"]
        # add id
        alert.add_context({"ident": "ident"})
        self.assertEqual(
            alert.context, {"ident": "ident", "testing": True, "created": timestamp}
        )
        # overwrite id
        alert.add_context({"ident": "new_ident"})
        self.assertEqual(
            alert.context, {"ident": "new_ident", "testing": True, "created": timestamp}
        )
        # add/remove children
        alert.add_child("uuid_child1")
        self.assertEqual(
            alert.context,
            {
                "ident": "new_ident",
                "testing": True,
                "parent_to": ["uuid_child1"],
                "created": timestamp,
            },
        )
        alert.add_child("uuid_child2")
        self.assertEqual(
            alert.context,
            {
                "ident": "new_ident",
                "testing": True,
                "parent_to": ["uuid_child1", "uuid_child2"],
                "created": timestamp,
            },
        )
        alert.remove_child("uuid_child1")
        self.assertEqual(
            alert.context,
            {
                "ident": "new_ident",
                "testing": True,
                "parent_to": ["uuid_child2"],
                "created": timestamp,
            },
        )
        alert.remove_child("uuid_not_there")
        self.assertEqual(
            alert.context,
            {
                "ident": "new_ident",
                "testing": True,
                "parent_to": ["uuid_child2"],
                "created": timestamp,
            },
        )
        # add/remove parent
        alert.set_parent("uuid_parent")
        self.assertEqual(
            alert.context,
            {
                "ident": "new_ident",
                "testing": True,
                "parent_to": ["uuid_child2"],
                "related_to": "uuid_parent",
                "created": timestamp,
            },
        )
        alert.remove_parent("uuid_parent")
        self.assertEqual(
            alert.context,
            {
                "ident": "new_ident",
                "testing": True,
                "parent_to": ["uuid_child2"],
                "created": timestamp,
            },
        )

    def test_from_ical_conversion(self):
        expiration = (dt.datetime.now(get_default_tz()) + dt.timedelta(minutes=40)).replace(
            microsecond=0
        )
        ical_vevent = [
            ("BEGIN", b"VEVENT"),
            ("SUMMARY", icalendar.vText("alert_name")),
            ("DTSTART", icalendar.vDDDTypes(expiration)),
            ("DTEND", icalendar.vDDDTypes(expiration + dt.timedelta(hours=1))),
            ("DTSTAMP", icalendar.vDDDTypes(expiration)),
            ("UID", icalendar.vText("ident")),
            ("SEQUENCE", 0),
            ("CLASS", icalendar.vText("PUBLIC")),
            ("DESCRIPTION", icalendar.vText("")),
            ("LAST-MODIFIED", icalendar.vDDDTypes(expiration)),
            ("LOCATION", icalendar.vText("")),
            ("STATUS", icalendar.vText("CONFIRMED")),
            ("TRANSP", icalendar.vText("TRANSPARENT")),
            ("X-MICROSOFT-CDO-ALLDAYEVENT", icalendar.vText("TRUE")),
            ("X-MICROSOFT-DISALLOW-COUNTER", icalendar.vText("FALSE")),
            ("BEGIN", b"VALARM"),
            ("ACTION", icalendar.vText("DISPLAY")),
            ("DESCRIPTION", icalendar.vText("")),
            ("TRIGGER", icalendar.vDDDTypes(dt.timedelta(minutes=-30))),
            ("END", b"VALARM"),
            ("END", b"VEVENT"),
            ("DAV_CALENDAR", "testcalendar"),
            ("DAV_SERVICE", "testservice"),
        ]
        alert_vevent = Alert.from_ical(ical_vevent)
        # Test alert properties
        self.assertEqual(alert_vevent.alert_type, AlertType.EVENT)
        self.assertEqual(alert_vevent.dav_type, DAVType.VEVENT)
        self.assertEqual(alert_vevent.calendar, "testcalendar")
        self.assertEqual(alert_vevent.service, "testservice")
        self.assertEqual(alert_vevent.priority, 5)
        self.assertEqual(alert_vevent.until, expiration + dt.timedelta(hours=1))
        self.assertIsNone(alert_vevent.repeat_days)
        self.assertIsNone(alert_vevent.repeat_frequency)
        self.assertEqual(alert_vevent.ident, "ident")
        self.assertEqual(alert_vevent.alert_name, "alert_name")
        self.assertIsNone(alert_vevent.audio_file)
        self.assertEqual(alert_vevent.is_expired, False)
        self.assertEqual(alert_vevent.expiration, expiration)
        self.assertEqual(
            alert_vevent.prenotification, expiration - dt.timedelta(minutes=30)
        )
        self.assertIsInstance(alert_vevent.time_to_expiration, dt.timedelta)

        # vtodo with expiration (=> AlertType.REMINDER)
        # with expiration only possible if created on the dav service (atm)
        creation = dt.datetime.now(get_default_tz()).replace(microsecond=0)
        ical_vtodo1 = [
            ("BEGIN", b"VTODO"),
            ("CREATED", icalendar.vDDDTypes(creation)),
            ("DUE", icalendar.vDDDTypes(creation + dt.timedelta(minutes=30))),
            ("DTSTAMP", icalendar.vDDDTypes(creation)),
            ("LAST-MODIFIED", icalendar.vDDDTypes(creation)),
            ("SUMMARY", icalendar.vText("alert_name")),
            ("UID", icalendar.vText("uuid_parent")),
            ("END", b"VTODO"),
        ]
        alert_vtodo1 = Alert.from_ical(ical_vtodo1)
        self.assertEqual(alert_vtodo1.alert_type, AlertType.REMINDER)
        self.assertEqual(alert_vtodo1.dav_type, DAVType.VTODO)
        self.assertEqual(alert_vtodo1.priority, 5)
        self.assertIsNone(alert_vtodo1.until)
        self.assertIsNone(alert_vtodo1.repeat_days)
        self.assertIsNone(alert_vtodo1.repeat_frequency)
        self.assertEqual(alert_vtodo1.ident, "uuid_parent")
        self.assertEqual(alert_vtodo1.alert_name, "alert_name")
        self.assertIsNone(alert_vtodo1.audio_file)
        self.assertEqual(alert_vtodo1.is_expired, False)
        self.assertEqual(alert_vtodo1.expiration, creation + dt.timedelta(minutes=30))
        self.assertIsNone(alert_vtodo1.prenotification)
        self.assertIsInstance(alert_vtodo1.time_to_expiration, dt.timedelta)

        # vtodo without expiration
        ical_vtodo2 = [
            ("BEGIN", b"VTODO"),
            ("CREATED", icalendar.vDDDTypes(creation)),
            ("DTSTAMP", icalendar.vDDDTypes(creation)),
            ("LAST-MODIFIED", icalendar.vDDDTypes(creation)),
            ("RELATED-TO", icalendar.vText("uuid_parent")),
            ("SUMMARY", icalendar.vText("alert_name")),
            ("UID", icalendar.vText("uuid_child")),
            ("END", b"VTODO"),
        ]
        alert_vtodo2 = Alert.from_ical(ical_vtodo2)
        self.assertEqual(alert_vtodo2.alert_type, AlertType.TODO)
        self.assertEqual(alert_vtodo2.dav_type, DAVType.VTODO)
        self.assertEqual(alert_vtodo2.priority, 5)
        self.assertIsNone(alert_vtodo2.until)
        self.assertIsNone(alert_vtodo2.repeat_days)
        self.assertIsNone(alert_vtodo2.repeat_frequency)
        self.assertEqual(alert_vtodo2.ident, "uuid_child")
        self.assertEqual(alert_vtodo2.related_to, "uuid_parent")
        self.assertEqual(alert_vtodo2.alert_name, "alert_name")
        self.assertIsNone(alert_vtodo2.audio_file)
        self.assertEqual(alert_vtodo2.is_expired, False)
        self.assertIsNone(alert_vtodo2.expiration)
        self.assertIsNone(alert_vtodo2.prenotification)
        self.assertEqual(alert_vtodo2.time_to_expiration.total_seconds(), 0)

        # parent/child (context) logic test
        # ical_vtodo1 is the parent of ical_vtodo2
        # by now only available for todos (=lists)
        from ovos_skill_alerts.util.dav_utils import _add_relations

        alerts = _add_relations([ical_vtodo1, ical_vtodo2])
        alert1, alert2 = alerts
        self.assertIn("uuid_child", alert1.children)
        self.assertEqual(alert2.related_to, "uuid_parent")


@unittest.skip('Work in progress')
class TestAlertManager(unittest.TestCase):
    manager_path = join(dirname(__file__), "test_cache")
    bus = FakeBus()

    def _init_alert_manager(self, wipe=True):
        alert_expired = Mock()
        alert_prenotification = Mock()

        if wipe:
            # Load empty cache
            test_file = join(self.manager_path, "alerts.json")
            if isfile(test_file):
                remove(test_file)
        
        scheduler = EventSchedulerInterface("test", bus=self.bus)
        alert_manager = AlertManager(
            self.manager_path,
            scheduler,
            (
                alert_prenotification,
                alert_expired,
            ),
        )
        return alert_manager

    def clear_storage(self, manager: AlertManager):
        manager._alerts_store.clear()
        manager._alerts_store.store()

    def test_alert_manager_init(self):
        called = Event()

        def alert_expired(activated_alert: Alert):
            self.assertIsInstance(activated_alert, Alert)
            self.assertFalse(activated_alert.has_repeat)
            called.set()

        def alert_prenotification(activated_alert: Alert):
            self.assertIsInstance(activated_alert, Alert)
            self.assertFalse(activated_alert.has_repeat)
            called.set()

        now_time = dt.datetime.now(dt.timezone.utc)
        future_alert = Alert.create(expiration=now_time + dt.timedelta(minutes=5))
        past_alert = Alert.create(expiration=now_time + dt.timedelta(minutes=-5))
        repeat_alert = Alert.create(
            expiration=now_time, repeat_frequency=dt.timedelta(seconds=1)
        )
        future_alert.add_context({"alert_reason": "expiration"})
        past_alert.add_context({"alert_reason": "expiration"})
        repeat_alert.add_context({"alert_reason": "expiration"})

        # Load empty cache
        test_file = join(self.manager_path, "alerts.json")
        if isfile(test_file):
            remove(test_file)
        scheduler = EventSchedulerInterface("test", bus=self.bus)
        alert_manager = AlertManager(
            self.manager_path,
            scheduler,
            (
                alert_prenotification,
                alert_expired,
            ),
        )
        self.assertEqual(alert_manager.missed_alerts, dict())
        self.assertEqual(alert_manager.pending_alerts, dict())
        self.assertEqual(alert_manager.active_alerts, dict())

        # Add valid alert
        alert_id = alert_manager.add_alert(future_alert)
        self.assertIn(alert_id, alert_manager.pending_alerts)
        self.assertEqual(len(scheduler.events.events), 1)
        self.assertEqual(
            alert_manager.pending_alerts[alert_id].expiration,
            future_alert.expiration,
        )
        self.assertEqual(alert_manager.get_alert_status(alert_id), AlertState.PENDING)

        # Remove valid alert
        alert_manager.rm_alert(alert_id)
        self.assertNotIn(alert_id, alert_manager.pending_alerts)
        self.assertEqual(len(scheduler.events.events), 0)
        self.assertEqual(alert_manager.get_alert_status(alert_id), AlertState.REMOVED)

        def _make_active_alert(alert):
            alert_id = alert.ident
            self.assertIn(alert_id, alert_manager.pending_alerts)
            data = alert.data
            context = alert.context
            message = Message(f"alert.{alert_id}", data, context)
            self.assertEqual(alert_manager.get_alert_status(alert_id), AlertState.PENDING)
            alert_manager._handle_alert_expiration(message)
            activated_alert = alert_manager._active_alerts.get(alert_id)
            self.assertTrue(called.wait(5))
            self.assertIsNotNone(activated_alert)
            self.assertEqual(alert_manager.get_alert_status(alert_id), AlertState.ACTIVE)
            return activated_alert

        # Handle dismiss active alert no repeat
        alert_manager.add_alert(past_alert)
        _make_active_alert(past_alert)
        dismissed_alert = alert_manager.rm_alert(past_alert.ident)
        self.assertEqual(dismissed_alert.data, past_alert.data)

        # Mark active alert as missed (no repeat)
        alert_id = alert_manager.add_alert(past_alert)
        _make_active_alert(past_alert)
        alert_manager.mark_alert_missed(alert_id)
        self.assertEqual(alert_manager.active_alerts, dict())
        self.assertIn(alert_id, alert_manager.missed_alerts)
        self.assertEqual(alert_manager.missed_alerts[alert_id].data, past_alert.data)
        self.assertEqual(alert_manager.get_alert_status(alert_id), AlertState.MISSED)

        # Dismiss missed alert
        missed_alert = alert_manager.rm_alert(alert_id)
        self.assertEqual(missed_alert.data, past_alert.data)
        self.assertEqual(alert_manager.missed_alerts, dict())

        # Schedule repeating alert
        alert_manager.add_alert(repeat_alert)
        activated_alert = _make_active_alert(repeat_alert)
        self.assertIn(repeat_alert.ident, alert_manager.pending_alerts)
        self.assertIn(activated_alert.ident, alert_manager.active_alerts)
        alert_manager.mark_alert_missed(activated_alert.ident)
        self.assertIn(activated_alert.ident, alert_manager.missed_alerts)
        self.assertIn(repeat_alert.ident, alert_manager.pending_alerts)
        self.assertNotIn(activated_alert.ident, alert_manager.active_alerts)

        # Dismiss activated alert
        missed_alert = alert_manager.rm_alert(activated_alert.ident)
        self.assertEqual(missed_alert.data, activated_alert.data)
        self.assertIn(repeat_alert.ident, alert_manager.pending_alerts)
        self.assertNotIn(activated_alert.ident, alert_manager.missed_alerts)
        self.assertNotIn(activated_alert.ident, alert_manager.active_alerts)

        # empty manager cache
        self.clear_storage(alert_manager)

    def test_alert_manager_dav_init_nodav(self):
        settings = ""
        dav_services = settings.split(",")
        alert_manager = self._init_alert_manager()
        credentials_file = join(self.manager_path, "dav_credentials.json")
        errors = alert_manager.init_dav_clients(dav_services, 15)
        self.assertEqual(alert_manager.dav_active, False)
        with open(credentials_file, "r") as f:
            jsondata = json.load(f)
        for service in dav_services:
            self.assertIn(service, jsondata)
        # check prepopulated cred_file
        dav_config = jsondata[""]
        self.assertIn("url", dav_config)
        self.assertEqual(all(key == "" for key in dav_config.values()), True)
        # no errors to report
        self.assertEqual(errors["dav.credentials.missing"], [])
        self.assertEqual(errors["dav.service.cant.connect"], [])
        self.assertEqual(len(alert_manager._scheduler.events.events), 0)
        remove(credentials_file)

    def test_alert_manager_dav_init_conncheck(self):
        credentials_file = join(self.manager_path, "dav_credentials.json")
        with JsonStorage(credentials_file) as credentials:
            credentials["testservice"] = {
                "url": "http://testservice",
                "username": "x",
                "password": "x",
                "ssl_verify_cert": "",
            }
        settings = "testservice"
        dav_services = settings.split(",")
        alert_manager = self._init_alert_manager()
        errors = alert_manager.init_dav_clients(dav_services, 15)
        self.assertEqual(alert_manager.dav_active, False)
        self.assertEqual(len(alert_manager._scheduler.events.events), 0)
        self.assertIn("testservice", errors["dav.service.cant.connect"])
        remove(credentials_file)

    def test_alert_manager_dav_init_no_conncheck(self):
        credentials_file = join(self.manager_path, "dav_credentials.json")
        with JsonStorage(credentials_file) as credentials:
            credentials["testservice"] = {
                "url": "http://testservice",
                "username": "x",
                "password": "x",
                "ssl_verify_cert": "",
            }
        settings = "testservice"
        dav_services = settings.split(",")
        alert_manager = self._init_alert_manager()
        errors = alert_manager.init_dav_clients(
            dav_services, 15, test_connectivity=False
        )
        self.assertEqual(alert_manager.dav_active, True)
        self.assertIn("testservice", alert_manager._dav_clients)
        self.assertEqual(errors["dav.credentials.missing"], [])
        self.assertEqual(errors["dav.service.cant.connect"], [])
        self.assertEqual(len(alert_manager._scheduler.events.events), 1)
        remove(credentials_file)
    
    def test_alert_manager_cache_file(self):
        manager = self._init_alert_manager()
        now_time = dt.datetime.now(dt.timezone.utc)
        # Check pending alert dumped to cache
        alert_time = now_time + dt.timedelta(hours=1)
        alert = Alert.create(expiration = alert_time,
                             alert_name='test1')
        ident = manager.add_alert(alert)
        with open(join(self.manager_path, 'alerts.json')) as f:
            alerts_data = json.load(f)
        self.assertEqual(set(alerts_data['pending'].keys()), {ident})
        # Check removed alert removed from cache
        alert_2 = Alert.create(expiration = alert_time,
                             alert_name='test2')
        ident_2 = manager.add_alert(alert_2)
        manager.rm_alert(ident)
        with open(join(self.manager_path, 'alerts.json')) as f:
            alerts_data = json.load(f)
        self.assertEqual(set(alerts_data['pending'].keys()), {ident_2})
        # Check missed alert added to cache
        missed_alert_time = now_time - dt.timedelta(hours=1)
        missed_alert_ident = str(time.time())
        alert = Alert.create(missed_alert_time, "missed test alert",
                             context={'ident': missed_alert_ident})
        manager._active_alerts[missed_alert_ident] = alert
        manager.mark_alert_missed(missed_alert_ident)
        with open(join(self.manager_path, 'alerts.json')) as f:
            alerts_data = json.load(f)
        self.assertEqual(set(alerts_data['missed'].keys()),
                         {missed_alert_ident})
        # Check dismissed missed alert removed from cache
        manager.rm_alert(missed_alert_ident)
        with open(join(self.manager_path, 'alerts.json')) as f:
            alerts_data = json.load(f)
        self.assertEqual(len(alerts_data['missed']), 0)

    def test_alert_manager_cache_load(self):
        
        alert_manager = self._init_alert_manager()

        now_time = dt.datetime.now(dt.timezone.utc)
        future_alert = Alert.create(now_time + dt.timedelta(minutes=5))
        repeat_alert = Alert.create(now_time,
                                    repeat_frequency=dt.timedelta(seconds=1),
                                    context = {"alert_reason": "expiration"})
        # Add alerts to manager
        alert_manager.add_alert(future_alert)
        alert_manager.add_alert(repeat_alert)
        # Cancel the event that would usually be cancelled on expiration
        alert_manager._cancel_scheduled_event(repeat_alert)
        alert_manager._handle_alert_expiration(repeat_alert)
        self.assertEqual(len(alert_manager.pending_alerts), 2)
        self.assertEqual(len(alert_manager.active_alerts), 1)
        self.assertEqual(alert_manager.missed_alerts, dict())
        # Check scheduled events
        self.assertEqual(len(alert_manager._scheduler.events.events), 2)
        # Shutdown manager
        alert_manager.shutdown()
        self.assertFalse(alert_manager._scheduler.events.events)
        # Create new manager
        new_manager = self._init_alert_manager(wipe=False)
        self.assertEqual(len(new_manager.pending_alerts), 2)
        self.assertEqual(len(new_manager.missed_alerts), 1)
        self.assertEqual(new_manager.active_alerts, dict())
        self.assertEqual(alert_manager.pending_alerts.keys(),
                         new_manager.pending_alerts.keys())
        # Check scheduled events
        self.assertEqual(len(new_manager._scheduler.events.events), 2)

    def test_get_user_alerts(self):

        alert_manager = self._init_alert_manager()
        alert_time = dt.datetime.now(dt.timezone.utc) + \
                dt.timedelta(minutes=random.randint(1, 60))
        active_alert = Alert.create(expiration=alert_time, alert_type=AlertType.ALARM)
        pending_alert = Alert.create(expiration=alert_time, alert_type=AlertType.EVENT)
        missed_alert = Alert.create(expiration=alert_time, alert_type=AlertType.REMINDER)
        alert_manager._active_alerts[active_alert.ident] = active_alert
        alert_manager._pending_alerts[pending_alert.ident] = pending_alert
        alert_manager._missed_alerts[missed_alert.ident] = missed_alert
        
        test_alerts = ((active_alert, AlertType.ALARM, "active"),
                       (pending_alert, AlertType.EVENT, "pending"),
                       (missed_alert, AlertType.REMINDER, "missed"))
        
        for alert, type_, state in test_alerts:
            test_dict = alert_manager.get_alerts(alert_type=type_)
            self.assertEqual(len(test_dict[state]), 1)
            self.assertEqual(test_dict[state][0].ident, alert.ident)
            self.assertEqual(test_dict[state][0].expiration, alert.expiration)
            self.assertEqual(test_dict[state][0].alert_type, alert.alert_type)

        # clean up
        self.clear_storage(alert_manager)

    def test_get_alert_user(self):
        # NOTE: user handling kept in alert manager
        # this could be interesting later on
        from ovos_skill_alerts.util.alert_manager import LOCAL_USER

        test_user = "another_user"
        alert_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
        alert = Alert.create(expiration=alert_time)

        self.assertEqual(alert.user, LOCAL_USER)

        alert.add_context({"user": test_user})
        self.assertEqual(alert.user, test_user)

    def test_get_ident(self):
        alert_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
        alert_auto_id = Alert.create(expiration=alert_time)
        alert_with_id = Alert.create(expiration=alert_time, context={"ident": "test"})

        self.assertIsNotNone(alert_auto_id.ident)
        self.assertEqual(alert_with_id.ident, "test")

    def test_sort_alerts_list(self):
        from ovos_skill_alerts.util.alert_manager import sort_alerts_list

        now_time = dt.datetime.now(dt.timezone.utc)
        alerts = list()

        for i in range(10):
            alert_time = now_time + dt.timedelta(minutes=random.randint(1, 60))
            alert = Alert.create(expiration=alert_time)
            alerts.append(alert)

        unsorted = deepcopy(alerts)
        alerts = sort_alerts_list(alerts)
        self.assertEqual(len(unsorted), len(alerts))
        self.assertEqual(len(alerts), 10)
        for i in range(1, len(alerts)):
            self.assertLessEqual(alerts[i - 1].expiration, alerts[i].expiration)

    def test_get_alert_by_type(self):
        from ovos_skill_alerts.util.alert_manager import get_alerts_by_type

        now_time = dt.datetime.now(dt.timezone.utc)
        alerts = list()

        for i in range(15):
            if i in range(5):
                alert_type = AlertType.ALARM
            elif i in range(10):
                alert_type = AlertType.TIMER
            else:
                alert_type = AlertType.REMINDER
            alert_time = now_time + dt.timedelta(minutes=random.randint(1, 60))
            alert = Alert.create(expiration=alert_time, alert_type=alert_type)
            alerts.append(alert)

        by_type = get_alerts_by_type(alerts)
        alarms = by_type[AlertType.ALARM]
        timers = by_type[AlertType.TIMER]
        reminders = by_type[AlertType.REMINDER]
        for alert in alarms:
            self.assertIsInstance(alert, Alert)
            self.assertEqual(alert.alert_type, AlertType.ALARM)
        for alert in timers:
            self.assertIsInstance(alert, Alert)
            self.assertEqual(alert.alert_type, AlertType.TIMER)
        for alert in reminders:
            self.assertIsInstance(alert, Alert)
            self.assertEqual(alert.alert_type, AlertType.REMINDER)

    def test_snooze_alert(self):
        manager = self._init_alert_manager()
        self.assertEqual(len(manager.pending_alerts), 0)

        alert_time = (now_time() + dt.timedelta(seconds=2)).replace(microsecond=0)
        # one time alert
        alert = Alert.create(alert_time,
                             context={"alert_reason": "expiration"})
        ident = manager.add_alert(alert)
        message = Message.deserialize(alert.serialize)
        time.sleep(2)
        manager._handle_alert_expiration(message)

        manager.snooze_alert(ident, dt.timedelta(minutes=10))
        self.assertEqual(len(manager.active_alerts), 0)
        self.assertEqual(len(manager.missed_alerts), 0)
        self.assertEqual(len(manager.pending_alerts), 1)
        self.assertIn(f'snoozed_{ident}', manager.pending_alerts)
        alert = manager.get_alert(f'snoozed_{ident}')
        print(alert.expiration)
        print(alert_time + dt.timedelta(minutes=10))
        self.assertEqual(alert.expiration,
                         alert_time + dt.timedelta(minutes=10))

        # alert with repeat frequency
        manager = self._init_alert_manager()
        self.assertEqual(len(manager.pending_alerts), 0)

        alert_time = (now_time() + dt.timedelta(seconds=2)).replace(microsecond=0)
        alert = Alert.create(alert_time,
                             repeat_frequency=dt.timedelta(hours=2),
                             context={"alert_reason": "expiration"})
        ident = manager.add_alert(alert)
        message = Message.deserialize(alert.serialize)
        time.sleep(2)
        manager._handle_alert_expiration(message)

        manager.snooze_alert(ident, dt.timedelta(minutes=10))
        self.assertEqual(len(manager.active_alerts), 0)
        self.assertEqual(len(manager.missed_alerts), 0)
        self.assertIn(f'snoozed_{ident}', manager.pending_alerts)
        # difference, the recurring lives on with another uid
        self.assertEqual(len(manager.pending_alerts), 2)
        alert = manager.get_alert(f'snoozed_{ident}')
        print(alert.expiration)
        print(alert_time + dt.timedelta(minutes=10))
        self.assertEqual(alert.expiration,
                         alert_time + dt.timedelta(minutes=10))

        # alert with repeat days
        manager = self._init_alert_manager()
        self.assertEqual(len(manager.pending_alerts), 0)

        alert_time = (now_time() + dt.timedelta(seconds=2)).replace(microsecond=0)
        alert = Alert.create(alert_time,
                             repeat_days={Weekdays.SAT, Weekdays.SUN},
                             context={"alert_reason": "expiration"})
        ident = manager.add_alert(alert)
        message = Message.deserialize(alert.serialize)
        time.sleep(2)
        manager._handle_alert_expiration(message)

        manager.snooze_alert(ident, dt.timedelta(minutes=10))
        self.assertEqual(len(manager.active_alerts), 0)
        self.assertEqual(len(manager.missed_alerts), 0)
        self.assertIn(f'snoozed_{ident}', manager.pending_alerts)
        self.assertEqual(len(manager.pending_alerts), 2)
        alert = manager.get_alert(f'snoozed_{ident}')
        print(alert.expiration)
        print(alert_time + dt.timedelta(minutes=10))
        self.assertEqual(alert.expiration,
                         alert_time + dt.timedelta(minutes=10))

    @patch("skill_alerts.util.alert_manager.uuid4")
    def test_reschedule_alert(self, mock_uuid4):
        mock_uuid4.return_value = "changed"
        manager = self._init_alert_manager()

        now = now_time()
        event1 = Alert.create(expiration=now + dt.timedelta(hours=1),
                              alert_type=AlertType.EVENT,
                              context={"ident":"event1"})
        event2 = Alert.create(expiration=now + dt.timedelta(hours=2),
                              alert_name="test_name",
                              alert_type=AlertType.EVENT,
                              context={"ident":"event2"})
        event3 = Alert.create(expiration=now + dt.timedelta(hours=3),
                              alert_type=AlertType.EVENT,
                              context={"ident":"event3"})
        event4 = Alert.create(expiration=now + dt.timedelta(hours=4),
                              repeat_frequency=86400,
                              alert_type=AlertType.EVENT,
                              context={"ident":"event4"})
        event4_2 = deepcopy(event4)
        event4_2.add_context({"ident": "event4_2"})
        event5 = Alert.create(expiration=now + dt.timedelta(hours=5),
                              repeat_days=EVERYDAY,
                              alert_type=AlertType.EVENT,
                              context={"ident":"event5"})
        event5_2 = deepcopy(event5)
        event5_2.add_context({"ident": "event5_2"})

        for ev in (event1, event2, event3, event4, event4_2, event5, event5_2):
            manager.add_alert(ev)

        # reschedule by positive timedelta margin
        manager.reschedule_alert(event1, dt.timedelta(minutes=15))

        self.assertEqual(len(manager._pending_alerts), 7)
        self.assertEqual(event1.expiration, now + dt.timedelta(hours=1,
                                                               minutes=15))
        name = nice_time(event1.created + dt.timedelta(hours=1, minutes=15),
                         'en-us', False, False, True)
        self.assertEqual(event1.alert_name, 
                         f"{name} event")  # check if alert name changed alongside
        self.assertEqual(event1.ident, "event1")

        # reschedule by negative timedelta margin
        manager.reschedule_alert(event2, dt.timedelta(minutes=-15))

        self.assertEqual(len(manager._pending_alerts), 7)
        self.assertEqual(event2.expiration, now + dt.timedelta(hours=1,
                                                               minutes=45))
        self.assertEqual(event2.alert_name, "test_name")  # check that name NOT changed, since it is not a default name
        self.assertEqual(event2.ident, "event2")

        # reschedule with a dt
        manager.reschedule_alert(event3, dt.datetime(now.year+1,1,1,1,1))

        self.assertEqual(len(manager._pending_alerts), 7)
        self.assertEqual(event3.expiration, dt.datetime(now.year+1,1,1,1,1))
        self.assertEqual(event3.ident, "event3")

        # reschedule repeat_fequency (affects all)
        manager.reschedule_alert(event4,
                                 dt.datetime(now.year+1,1,1,1,1),
                                 once=False)

        self.assertEqual(len(manager._pending_alerts), 7)
        self.assertEqual(event4.expiration, dt.datetime(now.year+1,1,1,1,1))
        self.assertEqual(event4.ident, "event4")
        self.assertTrue(event4.has_repeat)

        # reschedule repeat_days (affects all)
        manager.reschedule_alert(event5,
                                 dt.datetime(now.year+1,1,1,1,1),
                                 once=False)

        self.assertEqual(len(manager._pending_alerts), 7)
        self.assertEqual(event5.expiration, dt.datetime(now.year+1,1,1,1,1))
        self.assertEqual(event5.ident, "event5")
        self.assertTrue(event4.has_repeat)

        # reschedule repeat_fequency (only next recurrance)
        new_event = manager.reschedule_alert(event4_2,
                                             dt.datetime(now.year+1,1,2,1,1),
                                             once=True)

        self.assertEqual(len(manager._pending_alerts), 8)
        ## one day advance (repeat_frequency=3600)
        self.assertEqual(event4_2.expiration, now + dt.timedelta(days=1,
                                                               hours=4))
        self.assertEqual(new_event.expiration, dt.datetime(now.year+1,1,2,1,1))
        self.assertTrue(event4_2.has_repeat)
        self.assertFalse(new_event.has_repeat)
        self.assertEqual(event4_2.ident, "event4_2")
        self.assertEqual(new_event.ident, "changed")
        manager.rm_alert("changed")

        # reschedule repeat_days (only next recurrance)
        new_event = manager.reschedule_alert(event5_2,
                                             dt.datetime(now.year+1,1,3,1,1),
                                             once=True)

        self.assertEqual(len(manager._pending_alerts), 8)
        ## one day advance (repeat_days=EVERYDAY)
        self.assertEqual(event5_2.expiration, now + dt.timedelta(days=1,
                                                               hours=5))
        self.assertEqual(new_event.expiration, dt.datetime(now.year+1,1,3,1,1))
        self.assertTrue(event5_2.has_repeat)
        self.assertFalse(new_event.has_repeat)
        self.assertEqual(event5_2.ident, "event5_2")
        self.assertEqual(new_event.ident, "changed")
        manager.rm_alert("changed")
    
    def test_reschedule_repeat(self):
        manager = self._init_alert_manager()
        now = now_time()
        wd_now = now.weekday()

        #Alerts
        per_day = Alert.create(expiration=now,
                               repeat_days={Weekdays.SAT, Weekdays.FRI})
        frequency_alert = Alert.create(expiration=now,
                                       repeat_frequency=dt.timedelta(hours=1))
        without_repeat = Alert.create(expiration=now + dt.timedelta(hours=2))
        # TODO with end is simple property set -> test there
        with_end = Alert.create(expiration=now,
                                until=dt.datetime(2023,1,1,1,1, tzinfo=get_default_tz()))

        # repeat_days
        new_repeat = {Weekdays.FRI, Weekdays.SAT, Weekdays.MON}

        deltas = [wd - wd_now if wd - wd_now > 0 else wd - wd_now + 7
                    for wd in new_repeat]
        dts = [now + dt.timedelta(days=delta) for delta in deltas]
        dts.sort()
        
        manager.reschedule_repeat(per_day, new_repeat)
        self.assertEqual(len(per_day.repeat_days), 3)
        self.assertEqual(per_day.expiration, dts[0])

        # repeat_frequency
        manager.reschedule_repeat(frequency_alert, dt.timedelta(hours=2))
        self.assertEqual(frequency_alert.repeat_frequency, dt.timedelta(hours=2))
        self.assertEqual(frequency_alert.expiration, now + dt.timedelta(hours=2))

        # without repeat
        manager.reschedule_repeat(without_repeat, dt.timedelta(hours=2))
        ## skip the next expiration
        without_repeat.advance()
        self.assertEqual(without_repeat.repeat_frequency, dt.timedelta(hours=2))
        self.assertEqual(without_repeat.expiration, now + dt.timedelta(hours=4))

        # todo 
        # event end
        

    def test_timer_gui(self):
        manager = self._init_alert_manager()
        
        now_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        timer_1_time = now_time + dt.timedelta(minutes=5)
        timer_1_name = '5 minute timer'
        timer_1 = Alert.create(timer_1_time, timer_1_name, AlertType.TIMER)

        # Add timer to GUI
        manager.add_timer_to_gui(timer_1)
        self.assertEqual(len(manager.active_gui_timers), 1)
        self.assertEqual(manager.active_gui_timers[0].data, timer_1.data)

        # Ignore adding duplicate timer to GUI
        manager.add_timer_to_gui(timer_1)
        self.assertEqual(len(manager.active_gui_timers), 1)
        self.assertEqual(manager.active_gui_timers[0].data, timer_1.data)

        # Add different timer at same time
        timer_2 = Alert.create(timer_1_time, 'timer 2', AlertType.TIMER)
        manager.add_timer_to_gui(timer_2)
        self.assertEqual(len(manager.active_gui_timers), 2)
        self.assertIn(manager.active_gui_timers[0].data,
                      (timer_1.data, timer_2.data))
        self.assertIn(manager.active_gui_timers[1].data,
                      (timer_1.data, timer_2.data))

        # Dismiss timer
        manager.dismiss_alert_from_gui(timer_2.ident)
        self.assertEqual(len(manager.active_gui_timers), 1)
        self.assertEqual(manager.active_gui_timers[0].data, timer_1.data)

        # Add timer with the same name at a later time
        timer_3_time = now_time + dt.timedelta(minutes=6)
        timer_3 = Alert.create(timer_3_time, timer_1_name, AlertType.TIMER)
        manager.add_timer_to_gui(timer_3)
        self.assertEqual(len(manager.active_gui_timers), 2)
        self.assertEqual(manager.active_gui_timers[0].data, timer_1.data)
        self.assertEqual(manager.active_gui_timers[1].data, timer_3.data)

    @patch("skill_alerts.util.alert_manager.get_dav_items")
    def test_dav_sync(self, mock_get_dav_items):

        # Alert on DAV, not present locally
        now = now_time()
        expiration = now + dt.timedelta(minutes=30)
        alert = Alert.create(
            expiration=expiration,
            alert_type=AlertType.REMINDER,
            alert_name="dav reminder",
            dav_service="testservice",
            dav_calendar="testcalendar",
            context=dict(ident="sync_test"),
        )

        mock_get_dav_items.return_value = [alert]
        manager = self._init_alert_manager()
        manager._dav_clients = {"testservice": "dummy"}  # arbitrary
        fake_calendar = FakeCalendar()
        manager.get_dav_calendars = Mock(return_value=[fake_calendar])
        manager.get_dav_calendar = Mock(return_value=fake_calendar)
        manager.sync_dav()
        self.assertEqual(len(manager.pending_alerts), 1)
        self.assertEqual(alert.synchronized, True)
        self.assertIn("sync_test", manager.synchron_ids)

        # present locally, but Alert got edited upstream
        alert = Alert.create(
            expiration=expiration + dt.timedelta(minutes=10),
            prenotification=-1800,
            alert_type=AlertType.REMINDER,
            alert_name="edited dav reminder",
            dav_service="testservice",
            dav_calendar="testcalendar",
            context=dict(ident="sync_test"),
        )
        mock_get_dav_items.return_value = [alert]
        manager.sync_dav()
        self.assertEqual(len(manager.pending_alerts), 1)
        alert_locally = manager.get_alert("sync_test")  # type: Alert
        self.assertEqual(alert_locally.alert_name, "edited dav reminder")
        self.assertEqual(alert_locally.expiration, now + dt.timedelta(minutes=40))
        self.assertEqual(alert_locally.prenotification, now + dt.timedelta(minutes=10))
        self.assertEqual(len(manager.pending_alerts), 1)

        alert = manager.get_alert("sync_test")
        alert.synchronized = False
        manager._synchron_ids = set()
        # Alert is stored locally, not on dav
        mock_get_dav_items.return_value = []
        fake_calendar.save_event = Mock()
        self.assertIn("sync_test", manager.pending_alerts)
        manager.sync_dav()
        fake_calendar.save_event.assert_called_once()
        self.assertIn("sync_test", manager.synchron_ids)
        self.assertEqual(len(manager.pending_alerts), 1)

        # Alert is purposely taken from dav, so remove locally
        # this requires that the uuid was synced prior
        # (and is not active or missed)
        manager.sync_dav()
        self.assertEqual(len(manager.synchron_ids), 0)
        self.assertEqual(len(manager.pending_alerts), 0)

        # clean up
        self.clear_storage(manager)


@unittest.skip('Work in progress')
class TestParseUtils(unittest.TestCase):
    def test_round_nearest_minute(self):
        from ovos_skill_alerts.util.parse_utils import round_nearest_minute

        now_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        alert_time = now_time + dt.timedelta(minutes=9, seconds=5)
        rounded = round_nearest_minute(alert_time)
        self.assertEqual(rounded, alert_time)

        rounded = round_nearest_minute(alert_time, dt.timedelta(minutes=5))
        self.assertEqual(rounded, alert_time.replace(second=0))

    def test_spoken_time_remaining(self):
        # w/ datetime
        now_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        seconds_alert = now_time + dt.timedelta(minutes=59, seconds=59)
        to_speak = spoken_duration(seconds_alert, now_time)
        self.assertTrue(
            all([word for word in ("minutes", "seconds") if word in to_speak.split()])
        )
        self.assertEqual(to_speak, "fifty nine minutes fifty nine seconds")

        minutes_alert = now_time + dt.timedelta(hours=23, minutes=59, seconds=59)
        to_speak = spoken_duration(minutes_alert, now_time)
        self.assertTrue(
            all([word for word in ("hours", "minutes") if word in to_speak.split()])
        )
        self.assertNotIn("seconds", to_speak.split())
        self.assertEqual(to_speak, "twenty three hours fifty nine minutes")

        hours_alert = now_time + dt.timedelta(days=6, hours=23, minutes=59, seconds=59)
        to_speak = spoken_duration(hours_alert, now_time)
        self.assertTrue(
            all([word for word in ("days", "hours") if word in to_speak.split()])
        )
        self.assertTrue(
            all(
                [
                    not word
                    for word in ("minutes", "seconds")
                    if word in to_speak.split()
                ]
            )
        )
        self.assertEqual(to_speak, "six days  twenty three hours")

        days_alert = now_time + dt.timedelta(
            weeks=1, days=1, hours=1, minutes=1, seconds=1
        )
        to_speak = spoken_duration(days_alert, now_time)
        self.assertTrue(all([word for word in ("days",) if word in to_speak.split()]))
        self.assertTrue(
            all(
                [
                    not word
                    for word in ("hours", "minutes", "seconds")
                    if word in to_speak.split()
                ]
            )
        )
        self.assertEqual(to_speak, "eight days ")

        # w/ timedelta
        eight_hours = dt.timedelta(hours=8)
        to_speak = spoken_duration(eight_hours)
        self.assertTrue(all([word for word in ("hours",) if word in to_speak.split()]))
        self.assertTrue(
            all(
                [
                    not word
                    for word in ("days", "minutes", "seconds")
                    if word in to_speak.split()
                ]
            )
        )
        self.assertEqual(to_speak, "eight hours")
        

    @patch("skill_alerts.util.parse_utils.use_24h_format")
    def test_get_default_alert_name(self, mock_use_24h_format):
        from ovos_skill_alerts.util.parse_utils import get_default_alert_name

        mock_use_24h_format.return_value = False

        now_time = dt.datetime.now(dt.timezone.utc)
        timer_time = now_time + dt.timedelta(minutes=10)
        self.assertEqual(
            get_default_alert_name(timer_time, AlertType.TIMER, now_time),
            "ten minutes timer",
        )
        timer_time = now_time + dt.timedelta(hours=6, seconds=1)
        self.assertEqual(
            get_default_alert_name(timer_time, AlertType.TIMER, now_time),
            "six hours timer",
        )

        alarm_time = (now_time + dt.timedelta(days=1)).replace(
            hour=8, minute=0, second=0
        )
        self.assertEqual(
            get_default_alert_name(alarm_time, AlertType.ALARM), "8:00 AM alarm"
        )
        reminder_time = alarm_time + dt.timedelta(hours=12)
        self.assertEqual(
            get_default_alert_name(reminder_time, AlertType.REMINDER),
            "8:00 PM reminder",
        )

        mock_use_24h_format.return_value = True
        
        self.assertEqual(
            get_default_alert_name(alarm_time, AlertType.ALARM),
            "08:00 alarm",
        )
        self.assertEqual(
            get_default_alert_name(reminder_time, AlertType.REMINDER),
            "20:00 reminder",
        )

    def test_Tokens(self):
        from ovos_skill_alerts.util.parse_utils import tokenize_utterance, Tokens

        daily = _get_message_from_file("create_alarm_daily.json")
        tokens = tokenize_utterance(daily)
        self.assertIsInstance(tokens, Tokens)
        self.assertEqual(tokens, ["create", "an", "alarm", "for 10", "daily"])
        self.assertEqual(tokens.unmatched(), ["an", "for 10"])

        weekly = _get_message_from_file("create_alarm_every_tuesday.json")
        tokens = tokenize_utterance(weekly)
        self.assertEqual(tokens, ["set", "an", "alarm", "for 9 AM", "every", "tuesday"])
        self.assertEqual(tokens.unmatched(), ["an", "for 9 AM", "tuesday"])

        weekdays = _get_message_from_file("create_alarm_weekdays.json")
        tokens = tokenize_utterance(weekdays)
        self.assertEqual(tokens, ["set", "an", "alarm", "for 8 AM on", "weekdays"])
        self.assertEqual(tokens.unmatched(), ["an", "for 8 AM on"])

        weekends = _get_message_from_file("wake_me_up_weekends.json")
        tokens = tokenize_utterance(weekends)
        self.assertEqual(tokens, ["wake me up", "at 9 30 AM on", "weekends"])
        self.assertEqual(tokens.unmatched(), ["at 9 30 AM on"])

        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        tokens = tokenize_utterance(wakeup_at)
        self.assertEqual(tokens, ["neon", "wake me up", "at 7 AM"])
        self.assertEqual(tokens.unmatched(), ["neon", "at 7 AM"])

        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")
        tokens = tokenize_utterance(wakeup_in)
        self.assertEqual(tokens, ["wake me up", "in 8 hours"])
        self.assertEqual(tokens.unmatched(), ["in 8 hours"])

        multi_day_repeat = _get_message_from_file("alarm_every_monday_thursday.json")
        tokens = tokenize_utterance(multi_day_repeat)
        self.assertEqual(tokens, ["wake me up", "every", "monday and thursday at 9 AM"])
        self.assertEqual(tokens.unmatched(), ["monday and thursday at 9 AM"])

        # TODO if this is a real issue, its an intent parser problem
        # if STT sends "Alarm in ..." it should be tagged as such
        # capitalized = _get_message_from_file("alarm_capitalized_vocab.json")
        # tokens = tokenize_utterance(capitalized)
        # self.assertEqual(tokens, ['alarm', 'in 30 minutes'])

    def test_parse_repeat_from_message(self):
        from ovos_skill_alerts.util.parse_utils import parse_repeat_from_message, tokenize_utterance

        daily = _get_message_from_file("create_alarm_daily.json")
        repeat = parse_repeat_from_message(daily)
        self.assertIsInstance(repeat, list)
        self.assertEqual(
            repeat,
            [
                Weekdays.MON,
                Weekdays.TUE,
                Weekdays.WED,
                Weekdays.THU,
                Weekdays.FRI,
                Weekdays.SAT,
                Weekdays.SUN,
            ],
        )

        weekly = _get_message_from_file("create_alarm_every_tuesday.json")
        tokens = tokenize_utterance(weekly)
        repeat = parse_repeat_from_message(weekly, tokens)
        self.assertNotIn("tuesday", tokens)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [Weekdays.TUE])

        weekdays = _get_message_from_file("create_alarm_weekdays.json")
        repeat = parse_repeat_from_message(weekdays)
        self.assertIsInstance(repeat, list)
        self.assertEqual(
            repeat,
            [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI],
        )

        weekends = _get_message_from_file("wake_me_up_weekends.json")
        repeat = parse_repeat_from_message(weekends)
        self.assertEqual(repeat, [Weekdays.SAT, Weekdays.SUN])

        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        repeat = parse_repeat_from_message(wakeup_at)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [])

        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")
        repeat = parse_repeat_from_message(wakeup_in)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [])

        multi_day_repeat = _get_message_from_file("alarm_every_monday_thursday.json")
        tokens = tokenize_utterance(multi_day_repeat)
        repeat = parse_repeat_from_message(multi_day_repeat, tokens)
        self.assertIsInstance(repeat, list)
        self.assertEqual(repeat, [Weekdays.MON, Weekdays.THU])
        self.assertEqual(tokens, ["wake me up", "every", "and", "at 9 AM"])

        daily_reminder = _get_message_from_file(
            "remind_me_for_duration_to_action_every_repeat.json"
        )
        repeat = parse_repeat_from_message(daily_reminder)
        self.assertIsInstance(repeat, list)
        self.assertEqual(
            repeat,
            [
                Weekdays.MON,
                Weekdays.TUE,
                Weekdays.WED,
                Weekdays.THU,
                Weekdays.FRI,
                Weekdays.SAT,
                Weekdays.SUN,
            ],
        )

        every_12_hours_reminder = _get_message_from_file(
            "reminder_every_interval_to_action_for_duration.json"
        )
        tokens = tokenize_utterance(every_12_hours_reminder)
        repeat = parse_repeat_from_message(every_12_hours_reminder, tokens)
        self.assertEqual(repeat, dt.timedelta(hours=12))
        self.assertEqual(
            tokens,
            ["remind me", "every", "to take my antibiotics", "for the next", "week"],
        )

        every_8_hours_reminder = _get_message_from_file(
            "set_reminder_to_action_every_interval_until_end.json"
        )
        tokens = tokenize_utterance(every_8_hours_reminder)
        repeat = parse_repeat_from_message(every_8_hours_reminder, tokens)
        self.assertEqual(repeat, dt.timedelta(hours=8))
        self.assertEqual(
            tokens,
            ["set", "a", "reminder", "to rotate logs", "every", "until", "next sunday"],
        )

    def test_parse_end_condition_from_message(self):
        from ovos_skill_alerts.util.parse_utils import parse_end_condition_from_message

        now_time = dt.datetime.now(dt.timezone.utc)

        for_the_next_four_weeks = _get_message_from_file(
            "remind_me_for_duration_to_action_every_repeat.json"
        )
        for_the_next_week = _get_message_from_file(
            "reminder_every_interval_to_action_for_duration.json"
        )
        until_next_sunday = _get_message_from_file(
            "set_reminder_to_action_every_interval_until_end.json"
        )

        next_month = parse_end_condition_from_message(for_the_next_four_weeks)
        if isinstance(next_month, dt.timedelta):
            next_month += now_time
        self.assertEqual(next_month.date(), (now_time + dt.timedelta(weeks=4)).date())

        next_week = parse_end_condition_from_message(for_the_next_week)
        if isinstance(next_week, dt.timedelta):
            next_week += now_time
        self.assertEqual(next_week.date(), (now_time + dt.timedelta(days=7)).date())

        next_sunday = parse_end_condition_from_message(until_next_sunday)
        if isinstance(next_week, dt.timedelta):
            next_sunday += now_time
        self.assertEqual(next_sunday.weekday(), Weekdays.SUN)
        self.assertGreaterEqual(next_sunday, now_time)

    def test_parse_alert_time_from_message_alarm(self):
        from ovos_skill_alerts.util.parse_utils import parse_alert_time_from_message, tokenize_utterance

        daily = _get_message_from_file("create_alarm_daily.json")
        alert_time = parse_alert_time_from_message(daily)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertIn(alert_time.time(), (dt.time(hour=10), dt.time(hour=22)))

        weekly = _get_message_from_file("create_alarm_every_tuesday.json")
        tokens = tokenize_utterance(weekly)
        alert_time = parse_alert_time_from_message(weekly, tokens)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=9))
        self.assertNotIn("for 9 am", tokens)

        weekdays = _get_message_from_file("create_alarm_weekdays.json")
        alert_time = parse_alert_time_from_message(weekdays)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=8))

        weekends = _get_message_from_file("wake_me_up_weekends.json")
        alert_time = parse_alert_time_from_message(weekends)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=9, minute=30))

        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        alert_time = parse_alert_time_from_message(wakeup_at)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=7))

        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")
        alert_time = parse_alert_time_from_message(wakeup_in).replace(microsecond=0)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.tzinfo, dt.timezone(alert_time.utcoffset()))

        valid_alert_time = dt.datetime.now(tzlocal()).replace(
            microsecond=0
        ) + dt.timedelta(hours=8)

        self.assertEqual(valid_alert_time.tzinfo, tzlocal())
        self.assertAlmostEqual(alert_time.timestamp(), valid_alert_time.timestamp(), 0)

        multi_day_repeat = _get_message_from_file("alarm_every_monday_thursday.json")
        alert_time = parse_alert_time_from_message(multi_day_repeat)
        self.assertIsInstance(alert_time, dt.datetime)
        self.assertEqual(alert_time.time(), dt.time(hour=9))

    def test_parse_alert_time_from_message_timer(self):
        from ovos_skill_alerts.util.parse_utils import parse_alert_time_from_message

        no_name_10_minutes = _get_message_from_file("set_time_timer.json")
        baking_12_minutes = _get_message_from_file("start_named_timer.json")
        bread_20_minutes = _get_message_from_file("start_timer_for_name.json")
        no_name_utc = parse_alert_time_from_message(no_name_10_minutes)
        no_name_local = parse_alert_time_from_message(
            no_name_10_minutes, timezone=tzlocal()
        )
        baking_utc = parse_alert_time_from_message(baking_12_minutes)
        baking_local = parse_alert_time_from_message(
            baking_12_minutes, timezone=tzlocal()
        )
        bread_utc = parse_alert_time_from_message(bread_20_minutes)
        bread_local = parse_alert_time_from_message(
            bread_20_minutes, timezone=tzlocal()
        )
        self.assertAlmostEqual(no_name_utc.timestamp(), no_name_local.timestamp(), 0)
        self.assertAlmostEqual(baking_utc.timestamp(), baking_local.timestamp(), 0)
        self.assertAlmostEqual(bread_utc.timestamp(), bread_local.timestamp(), 0)

    def test_parse_alert_time_from_message_reminder(self):
        # TODO
        pass

    def test_parse_timeframe_from_message(self):
        from ovos_skill_alerts.util.parse_utils import parse_timeframe_from_message

        begin_end = _get_message_from_file("query_alerts_timeframe2.json")
        only_begin_time = _get_message_from_file("query_alerts_timeframe3.json")
        only_begin_date = _get_message_from_file("query_alerts_timeframe4.json")

        begin, end = parse_timeframe_from_message(begin_end, timezone=dt.timezone.utc)
        self.assertEqual(end, dt.datetime(2024, 2, 2, 11, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(begin, dt.datetime(2024, 2, 2, 10, 0, tzinfo=dt.timezone.utc))

        begin, end = parse_timeframe_from_message(only_begin_time, timezone=dt.timezone.utc)
        self.assertIsInstance(begin, dt.datetime)
        self.assertEqual(begin, dt.datetime(2024, 2, 2, 10, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(end, None)

        begin, end = parse_timeframe_from_message(only_begin_date, timezone=dt.timezone.utc)
        self.assertIsInstance(begin, dt.datetime)
        self.assertEqual(begin, dt.datetime(2024, 2, 2, 0, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(end, dt.datetime(2024, 2, 2, 23, 59, 59, tzinfo=dt.timezone.utc))

    def test_parse_timedelta_from_message(self):
        from ovos_skill_alerts.util.parse_utils import parse_timedelta_from_message

        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        if now.replace(hour=8, minute=0, second=0) < now:
            eight_am = now.replace(hour=8, minute=0, second=0) + dt.timedelta(days=1)
        else:
            eight_am = now.replace(hour=8, minute=0, second=0)

        snooze_until_time = _get_message_from_file("snooze_until_time_converse.json")
        snooze_for_duration = _get_message_from_file("snooze_for_duration_converse.json")

        dur = parse_timedelta_from_message(snooze_until_time,
                                           anchor_time=now)
        self.assertEqual(dur, eight_am - now)

        dur = parse_timedelta_from_message(snooze_for_duration,
                                           anchor_time=now)
        self.assertEqual(dur, dt.timedelta(minutes=5))

    def test_parse_alert_priority_from_message(self):
        # TODO
        pass

    def test_parse_audio_file_from_message(self):
        # TODO
        pass

    def test_parse_alert_name_from_message(self):
        from ovos_skill_alerts.util.parse_utils import parse_alert_name_from_message

        monday_thursday_alarm = _get_message_from_file(
            "alarm_every_monday_thursday.json"
        )
        daily_alarm = _get_message_from_file("create_alarm_daily.json")
        tuesday_alarm = _get_message_from_file("create_alarm_every_tuesday.json")
        weekday_alarm = _get_message_from_file("create_alarm_weekdays.json")
        wakeup_at_time_alarm = _get_message_from_file("wake_me_up_at_time_alarm.json")
        wakeup_in_time_alarm = _get_message_from_file("wake_me_up_in_time_alarm.json")
        wakeup_weekends = _get_message_from_file("wake_me_up_weekends.json")

        set_unnamed_timer = _get_message_from_file("set_time_timer.json")
        start_unnamed_timer = _get_message_from_file("start_timer_for_time.json")
        baking_timer = _get_message_from_file("start_named_timer.json")
        bread_timer = _get_message_from_file("start_timer_for_name.json")

        exercise_reminder = _get_message_from_file(
            "remind_me_for_duration_to_action_every_repeat.json"
        )
        dinner_reminder = _get_message_from_file("reminder_at_time_to_action.json")
        antibiotics_reminder = _get_message_from_file(
            "reminder_every_interval_to_action_for_duration.json"
        )
        break_reminder = _get_message_from_file("reminder_in_duration_to_action.json")
        meeting_reminder = _get_message_from_file("reminder_to_action_at_time.json")
        alt_dinner_reminder = _get_message_from_file(
            "reminder_to_action_in_duration.json"
        )
        medication_reminder = _get_message_from_file(
            "set_action_reminder_for_time.json"
        )
        rotate_logs_reminder = _get_message_from_file(
            "set_reminder_to_action_every_interval_until_end.json"
        )

        with open(join(dirname(dirname(__file__)),
                       "locale", "en-us", "vocab", "noise_words.voc")) as f:
            noise_words = f.read().split('\n')

        self.assertEqual(parse_alert_name_from_message(monday_thursday_alarm,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(daily_alarm,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(tuesday_alarm,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(weekday_alarm,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(wakeup_at_time_alarm,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(wakeup_weekends,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(wakeup_in_time_alarm,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(set_unnamed_timer,
                                                       noise_words=noise_words), "")
        self.assertEqual(parse_alert_name_from_message(start_unnamed_timer,
                                                       noise_words=noise_words), "")

        self.assertEqual(parse_alert_name_from_message(baking_timer,
                                                       noise_words=noise_words),
                        "baking",
        )
        self.assertEqual(parse_alert_name_from_message(bread_timer,
                                                       noise_words=noise_words),
                        "bread",
        )

        self.assertEqual(parse_alert_name_from_message(exercise_reminder,
                                                       noise_words=noise_words),
                        "exercise",
        )
        self.assertEqual(parse_alert_name_from_message(dinner_reminder,
                                                       noise_words=noise_words),
                         "start making dinner",
        )
        self.assertEqual(parse_alert_name_from_message(antibiotics_reminder,
                                                       noise_words=noise_words),
                         "take antibiotics",
        )
        self.assertEqual(parse_alert_name_from_message(break_reminder,
                                                       noise_words=noise_words),
                         "take break",
        )
        self.assertEqual(parse_alert_name_from_message(meeting_reminder,
                                                       noise_words=noise_words),
                         "start meeting",
        )
        self.assertEqual(parse_alert_name_from_message(alt_dinner_reminder,
                                                       noise_words=noise_words),
                         "start dinner",
        )
        self.assertEqual(parse_alert_name_from_message(medication_reminder,
                                                       noise_words=noise_words),
                         "medication",
        )
        self.assertEqual(parse_alert_name_from_message(rotate_logs_reminder,
                                                       noise_words=noise_words),
                         "rotate logs",
        )

    def test_parse_alert_context_from_message(self):
        from ovos_skill_alerts.util.parse_utils import LOCAL_USER, parse_alert_context_from_message

        test_message_no_context = Message("test", {}, {})
        test_message_local_user = Message(
            "test",
            {},
            {
                "user": "local",
                "timing": {
                    "handle_utterance": 1644629287.028714,
                    "transcribed": 1644629287.028714,
                    "save_transcript": 8.821487426757812e-06,
                    "text_parsers": 4.553794860839844e-05,
                },
                "ident": "1644629287",
            },
        )

        no_context = parse_alert_context_from_message(test_message_no_context)
        self.assertEqual(no_context["user"], LOCAL_USER)
        self.assertIsInstance(no_context["ident"], str)
        self.assertIsInstance(no_context["created"], float)

        local_user = parse_alert_context_from_message(test_message_local_user)
        self.assertEqual(local_user["user"], "local")
        self.assertEqual(local_user["ident"], "1644629287")
        self.assertEqual(local_user["created"], 1644629287.028714)
        self.assertIsInstance(local_user["timing"], dict)

    def test_build_alert_from_intent_alarm(self):
        from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

        daily = _get_message_from_file("create_alarm_daily.json")
        wakeup_at = _get_message_from_file("wake_me_up_at_time_alarm.json")
        wakeup_in = _get_message_from_file("wake_me_up_in_time_alarm.json")

        daily_alert_local = build_alert_from_intent(daily)
        # infuse utc timezone
        change_user_tz(daily, "UTC")
        daily_alert_utc = build_alert_from_intent(daily)

        def _validate_daily(alert: Alert):
            self.assertEqual(alert.alert_type, AlertType.ALARM)
            self.assertIsInstance(alert.priority, int)
            self.assertIsNone(alert.until)
            self.assertEqual(len(alert.repeat_days), 7)
            self.assertIsNone(alert.repeat_frequency)
            self.assertIsInstance(alert.context, dict)
            self.assertIsInstance(alert.alert_name, str)
            self.assertIsNone(alert.audio_file)
            self.assertFalse(alert.is_expired)
            self.assertGreaterEqual(alert.time_to_expiration, dt.timedelta(seconds=1))
            self.assertIn(alert.expiration.time(), (dt.time(hour=10), dt.time(hour=22)))

        _validate_daily(daily_alert_local)
        _validate_daily(daily_alert_utc)
        self.assertNotEqual(
            daily_alert_local.time_to_expiration.total_seconds(),
            daily_alert_utc.time_to_expiration.total_seconds(),
        )

        wakeup_at_alert_local = build_alert_from_intent(wakeup_at)
        # infuse utc timezone
        change_user_tz(wakeup_at, "UTC")
        wakeup_at_alert_utc = build_alert_from_intent(wakeup_at)

        def _validate_wakeup_at(alert: Alert):
            self.assertEqual(alert.alert_type, AlertType.ALARM)
            self.assertIsInstance(alert.priority, int)
            self.assertIsNone(alert.until)
            self.assertIsNone(alert.repeat_days)
            self.assertIsNone(alert.repeat_frequency)
            self.assertIsInstance(alert.context, dict)
            self.assertIsInstance(alert.alert_name, str)
            self.assertIsNone(alert.audio_file)
            self.assertFalse(alert.is_expired)
            self.assertGreaterEqual(alert.time_to_expiration, dt.timedelta(seconds=1))
            self.assertEqual(alert.expiration.time(), dt.time(hour=7))

        _validate_wakeup_at(wakeup_at_alert_local)
        _validate_wakeup_at(wakeup_at_alert_utc)
        self.assertEqual(
            wakeup_at_alert_local.alert_name, wakeup_at_alert_utc.alert_name
        )
        self.assertEqual(wakeup_at_alert_utc.alert_name, "7:00 AM alarm")
        self.assertNotEqual(
            wakeup_at_alert_local.time_to_expiration,
            wakeup_at_alert_utc.time_to_expiration,
        )

        wakeup_in_alert_local = build_alert_from_intent(wakeup_in)
        # infuse utc timezone
        change_user_tz(wakeup_in, "UTC")
        wakeup_in_alert_utc = build_alert_from_intent(wakeup_in)

        def _validate_wakeup_in(alert: Alert):
            self.assertEqual(alert.alert_type, AlertType.ALARM)
            self.assertIsInstance(alert.priority, int)
            self.assertIsNone(alert.until)
            self.assertIsNone(alert.repeat_days)
            self.assertIsNone(alert.repeat_frequency)
            self.assertIsInstance(alert.context, dict)
            self.assertIsInstance(alert.alert_name, str)
            self.assertIsNone(alert.audio_file)
            self.assertFalse(alert.is_expired)
            self.assertAlmostEqual(
                alert.time_to_expiration.total_seconds(),
                dt.timedelta(hours=8).total_seconds(),
                delta=2,
            )

        _validate_wakeup_in(wakeup_in_alert_local)
        _validate_wakeup_in(wakeup_in_alert_utc)
        self.assertAlmostEqual(
            wakeup_in_alert_local.time_to_expiration.total_seconds(),
            wakeup_in_alert_utc.time_to_expiration.total_seconds(),
            delta=2,
        )

    def test_build_alert_from_intent_timer(self):
        from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

        no_name_10_minutes = _get_message_from_file("set_time_timer.json")
        baking_12_minutes = _get_message_from_file("start_named_timer.json")
        bread_20_minutes = _get_message_from_file("start_timer_for_name.json")

        def _validate_alert_default_params(timer: Alert):
            self.assertEqual(timer.alert_type, AlertType.TIMER)
            self.assertIsInstance(timer.priority, int)
            self.assertIsNone(timer.until)
            self.assertIsNone(timer.repeat_days)
            self.assertIsNone(timer.repeat_frequency)
            self.assertIsInstance(timer.context, dict)
            self.assertIsInstance(timer.alert_name, str)
            self.assertIsNone(timer.audio_file)
            self.assertFalse(timer.is_expired)
            self.assertIsInstance(timer.time_to_expiration, dt.timedelta)
            self.assertIsInstance(timer.expiration, dt.datetime)

        no_name_timer_local = build_alert_from_intent(no_name_10_minutes)
        # infuse utc timezone
        change_user_tz(no_name_10_minutes, "UTC")
        no_name_timer_utc = build_alert_from_intent(no_name_10_minutes)

        _validate_alert_default_params(no_name_timer_utc)
        _validate_alert_default_params(no_name_timer_local)
        self.assertAlmostEqual(
            no_name_timer_local.time_to_expiration.total_seconds(),
            no_name_timer_utc.time_to_expiration.total_seconds(),
            0,
        )

        baking_timer_local = build_alert_from_intent(baking_12_minutes)
        _validate_alert_default_params(baking_timer_local)
        self.assertEqual(baking_timer_local.alert_name, "baking")

        bread_timer_local = build_alert_from_intent(bread_20_minutes)
        _validate_alert_default_params(bread_timer_local)
        self.assertEqual(bread_timer_local.alert_name, "bread")

    def test_build_alert_from_intent_reminder(self):
        from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

        def _validate_alert_default_params(reminder: Alert):
            self.assertEqual(reminder.alert_type, AlertType.REMINDER)
            self.assertIsInstance(reminder.priority, int)
            self.assertIsInstance(reminder.context, dict)
            self.assertIsInstance(reminder.alert_name, str)
            self.assertIsNone(reminder.audio_file)
            self.assertFalse(reminder.is_expired)
            self.assertIsInstance(reminder.time_to_expiration, dt.timedelta)
            self.assertIsInstance(reminder.expiration, dt.datetime)

        exercise_reminder = _get_message_from_file(
            "remind_me_for_duration_to_action_every_repeat.json"
        )
        exercise_reminder = build_alert_from_intent(exercise_reminder)

        _validate_alert_default_params(exercise_reminder)
        self.assertEqual(exercise_reminder.expiration.time(), dt.time(hour=10))
        self.assertEqual(exercise_reminder.alert_name, "exercise")
        self.assertEqual(len(exercise_reminder.repeat_days), 7)
        self.assertIsNone(exercise_reminder.repeat_frequency)
        dst_offset_diff = exercise_reminder.expiration.utcoffset() - \
                exercise_reminder.until.utcoffset()
        self.assertEqual(
            exercise_reminder.until,
            exercise_reminder.expiration + dt.timedelta(weeks=4) + dst_offset_diff,
        )

        dinner_reminder = _get_message_from_file("reminder_at_time_to_action.json")
        dinner_reminder = build_alert_from_intent(dinner_reminder)

        _validate_alert_default_params(dinner_reminder)
        self.assertEqual(dinner_reminder.expiration.time(), dt.time(hour=19))
        self.assertEqual(dinner_reminder.alert_name, "start making dinner")
        self.assertIsNone(dinner_reminder.repeat_days)
        self.assertIsNone(dinner_reminder.repeat_frequency)
        self.assertIsNone(dinner_reminder.until)

        antibiotics_reminder = _get_message_from_file(
            "reminder_every_interval_to_action_for_duration.json"
        )
        antibiotics_reminder = build_alert_from_intent(antibiotics_reminder)

        self.assertAlmostEqual(
            antibiotics_reminder.expiration.timestamp(),
            (antibiotics_reminder.created + dt.timedelta(hours=12)).timestamp(),
            delta=1,
        )
        self.assertEqual(antibiotics_reminder.alert_name, "take antibiotics")
        self.assertIsNone(antibiotics_reminder.repeat_days)
        self.assertEqual(antibiotics_reminder.repeat_frequency, dt.timedelta(hours=12))
        print(antibiotics_reminder.until - antibiotics_reminder.expiration)
        print(dt.timedelta(weeks=1))
        dst_offset_diff = antibiotics_reminder.expiration.utcoffset() -\
                antibiotics_reminder.until.utcoffset()
        self.assertEqual(
            antibiotics_reminder.until,
            antibiotics_reminder.expiration + dt.timedelta(weeks=1, hours=-12) + dst_offset_diff,
        )

        break_reminder = _get_message_from_file("reminder_in_duration_to_action.json")
        break_reminder = build_alert_from_intent(break_reminder)

        self.assertAlmostEqual(
            break_reminder.expiration.timestamp(),
            (break_reminder.created + dt.timedelta(hours=1)).timestamp(),
            delta=1,
        )
        self.assertEqual(break_reminder.alert_name, "take break")
        self.assertIsNone(break_reminder.repeat_days)
        self.assertIsNone(break_reminder.repeat_frequency)
        self.assertIsNone(break_reminder.until)

        meeting_reminder = _get_message_from_file("reminder_to_action_at_time.json")
        meeting_reminder = build_alert_from_intent(meeting_reminder)

        self.assertEqual(meeting_reminder.expiration.time(), dt.time(hour=10))
        self.assertEqual(meeting_reminder.alert_name, "start meeting")
        self.assertIsNone(meeting_reminder.repeat_days)
        self.assertIsNone(meeting_reminder.repeat_frequency)
        self.assertIsNone(meeting_reminder.until)

        alt_dinner_reminder = _get_message_from_file(
            "reminder_to_action_in_duration.json"
        )
        alt_dinner_reminder = build_alert_from_intent(alt_dinner_reminder)

        self.assertAlmostEqual(
            alt_dinner_reminder.expiration.timestamp(),
            (alt_dinner_reminder.created + dt.timedelta(hours=3)).timestamp(),
            delta=1,
        )
        self.assertEqual(alt_dinner_reminder.alert_name, "start dinner")
        self.assertIsNone(alt_dinner_reminder.repeat_days)
        self.assertIsNone(alt_dinner_reminder.repeat_frequency)
        self.assertIsNone(alt_dinner_reminder.until)

        # repeating event with a distrinct end datetime
        medication_reminder = _get_message_from_file(
            "set_action_reminder_for_time.json"
        )
        medication_reminder = build_alert_from_intent(medication_reminder)

        self.assertEqual(medication_reminder.expiration.time(), dt.time(hour=21))
        self.assertEqual(medication_reminder.alert_name, "medication")
        self.assertIsNone(medication_reminder.repeat_days)
        self.assertIsNone(medication_reminder.repeat_frequency)
        self.assertIsNone(medication_reminder.until)

        rotate_logs_reminder = _get_message_from_file(
            "set_reminder_to_action_every_interval_until_end.json"
        )
        rotate_logs_reminder = build_alert_from_intent(rotate_logs_reminder)

        self.assertAlmostEqual(
            rotate_logs_reminder.expiration.timestamp(),
            (rotate_logs_reminder.created + dt.timedelta(hours=8)).timestamp(),
            delta=1,
        )
        self.assertEqual(rotate_logs_reminder.alert_name, "rotate logs")
        self.assertIsNone(rotate_logs_reminder.repeat_days)
        self.assertEqual(rotate_logs_reminder.repeat_frequency, dt.timedelta(hours=8))

    def test_build_alert_from_intent_event(self):
        from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

        def _validate_alert_default_params(reminder: Alert):
            self.assertEqual(reminder.alert_type, AlertType.EVENT)
            self.assertIsInstance(reminder.priority, int)
            self.assertIsInstance(reminder.context, dict)
            self.assertIsInstance(reminder.alert_name, str)
            self.assertIsNone(reminder.audio_file)
            self.assertFalse(reminder.is_expired)
            self.assertIsInstance(reminder.time_to_expiration, dt.timedelta)
            self.assertIsInstance(reminder.expiration, dt.datetime)

        halloween_reminder = _get_message_from_file(
            "reminder_event_length_at_time.json"
        )
        halloween_reminder = build_alert_from_intent(halloween_reminder)

        _validate_alert_default_params(halloween_reminder)
        expiration = (halloween_reminder.created
                      + dt.timedelta(days=2)).replace(microsecond=0)
        self.assertEqual(halloween_reminder.expiration, expiration)
        self.assertEqual(halloween_reminder.alert_name, "halloween")
        self.assertIsNone(halloween_reminder.repeat_days)
        self.assertIsNone(halloween_reminder.repeat_frequency)
        self.assertEqual(
            halloween_reminder.until,
            halloween_reminder.expiration + dt.timedelta(hours=3),
        )


@unittest.skip('Work in progress')
class TestUIModels(unittest.TestCase):
    load_language("en")

    def test_build_timer_data(self):
        from ovos_skill_alerts.util.ui_models import build_timer_data

        now_time_valid = dt.datetime.now(dt.timezone.utc)
        invalid_alert = Alert.create(
            expiration=now_time_valid + dt.timedelta(hours=1),
            alert_name="test alert name",
            alert_type=AlertType.ALARM,
            context={"testing": True},
        )

        with self.assertRaises(ValueError):
            build_timer_data(invalid_alert)

        valid_alert = Alert.create(
            expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
            alert_name="test timer",
            alert_type=AlertType.TIMER,
            context={"testing": True, "start_time": now_time_valid},
        )
        timer_data = build_timer_data(valid_alert)
        self.assertEqual(
            set(timer_data.keys()),
            {
                "alertId",
                "backgroundColor",
                "expired",
                "percentRemaining",
                "timerName",
                "timeDelta",
            },
        )
        self.assertEqual(timer_data["alertId"], valid_alert.ident)
        self.assertAlmostEqual(timer_data["percentRemaining"], 1, 2)
        self.assertEqual(timer_data["timerName"], "test timer")
        self.assertIsInstance(timer_data["timeDelta"], str)

        time.sleep(1)
        new_timer_data = build_timer_data(valid_alert)
        self.assertLess(
            new_timer_data["percentRemaining"], timer_data["percentRemaining"]
        )
        self.assertAlmostEqual(timer_data["percentRemaining"], 1, 1)         

    @patch("skill_alerts.util.ui_models.use_24h_format")
    def test_build_alarm_data(self, mock_use_24h_format):        
        from ovos_skill_alerts.util.ui_models import build_alarm_data

        # Get tomorrow at 9 AM
        now_time_valid = dt.datetime.now(dt.timezone.utc)
        alarm_time = (now_time_valid + dt.timedelta(hours=24)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

        alarm = Alert.create(
            expiration=alarm_time,
            alert_name="Test Alarm",
            alert_type=AlertType.ALARM
        )

        mock_use_24h_format.return_value = False
        us_display = build_alarm_data(alarm)
        self.assertEqual(
            set(us_display.keys()),
            {"alarmTime", "alarmAmPm", "alarmName", "alarmExpired", "alarmIndex",
             "alarmRepeat", "alarmRepeatStr"},
        )
        self.assertEqual(us_display["alarmTime"], "9:00")
        self.assertEqual(us_display["alarmAmPm"], "AM")
        self.assertEqual(us_display["alarmName"], "Test Alarm")
        self.assertFalse(us_display["alarmExpired"])
        self.assertEqual(us_display["alarmIndex"], alarm.ident)
        self.assertEqual(us_display["alarmRepeatStr"], "Once")

        mock_use_24h_format.return_value = True
        metric_display = build_alarm_data(alarm)
        self.assertEqual(
            set(metric_display.keys()),
            {"alarmTime", "alarmAmPm", "alarmName", "alarmExpired", "alarmIndex",
             "alarmRepeat", "alarmRepeatStr"},
        )
        self.assertEqual(metric_display["alarmTime"], "09:00")
        self.assertEqual(metric_display["alarmAmPm"], "")
        self.assertEqual(metric_display["alarmName"], "Test Alarm")
        self.assertFalse(metric_display["alarmExpired"])
        self.assertEqual(metric_display["alarmIndex"], alarm.ident)
        self.assertEqual(metric_display["alarmRepeatStr"], "Once")

        # test repeating alarm (abbreviations)
        days = [Weekdays.MON, Weekdays.TUE, Weekdays.WED, Weekdays.THU, Weekdays.FRI]
        rep_alarm1 = Alert.create(
            expiration=alarm_time,
            alert_name="Test Alarm",
            alert_type=AlertType.ALARM,
            repeat_days=days
        )
        display = build_alarm_data(rep_alarm1)
        self.assertEqual(
            set(display.keys()),
            {"alarmTime", "alarmAmPm", "alarmName", "alarmExpired", "alarmIndex",
             "alarmRepeat", "alarmRepeatStr"},
        )
        self.assertEqual(display["alarmTime"], "09:00")
        self.assertEqual(display["alarmAmPm"], "")
        self.assertEqual(display["alarmName"], "Test Alarm")
        self.assertFalse(display["alarmExpired"])
        self.assertEqual(display["alarmIndex"], rep_alarm1.ident)
        self.assertEqual(display["alarmRepeatStr"], "MON-FRI")

        days = [Weekdays.MON, Weekdays.THU, Weekdays.FRI, Weekdays.SAT]
        rep_alarm2 = Alert.create(
            expiration=alarm_time,
            alert_name="Test Alarm",
            alert_type=AlertType.ALARM,
            repeat_days=days
        )
        display = build_alarm_data(rep_alarm2)
        self.assertEqual(
            set(display.keys()),
            {"alarmTime", "alarmAmPm", "alarmName", "alarmExpired", "alarmIndex",
             "alarmRepeat", "alarmRepeatStr"},
        )
        self.assertEqual(display["alarmTime"], "09:00")
        self.assertEqual(display["alarmAmPm"], "")
        self.assertEqual(display["alarmName"], "Test Alarm")
        self.assertFalse(display["alarmExpired"])
        self.assertEqual(display["alarmIndex"], rep_alarm2.ident)
        self.assertEqual(display["alarmRepeatStr"], "MON,THU-SAT")

        days = [Weekdays.MON, Weekdays.THU, Weekdays.SUN]
        rep_alarm3 = Alert.create(
            expiration=alarm_time,
            alert_name="Test Alarm",
            alert_type=AlertType.ALARM,
            repeat_days=days
        )
        display = build_alarm_data(rep_alarm3)
        self.assertEqual(
            set(display.keys()),
            {"alarmTime", "alarmAmPm", "alarmName", "alarmExpired", "alarmIndex",
             "alarmRepeat", "alarmRepeatStr"},
        )
        self.assertEqual(display["alarmTime"], "09:00")
        self.assertEqual(display["alarmAmPm"], "")
        self.assertEqual(display["alarmName"], "Test Alarm")
        self.assertFalse(display["alarmExpired"])
        self.assertEqual(display["alarmIndex"], rep_alarm3.ident)
        self.assertEqual(display["alarmRepeatStr"], "MON,THU,SUN")


@unittest.skip('Work in progress')
class TestSkillLoading(unittest.TestCase):
    """
    Test skill loading, intent registration, and langauge support. Test cases
    are generic, only class variables should be modified per-skill.
    """
    # Static parameters
    bus = FakeBus()
    messages = list()
    test_skill_id = 'test_skill.test'
    # Default Core Events
    default_events = ["mycroft.skill.enable_intent",
                      "mycroft.skill.disable_intent",
                      "mycroft.skill.set_cross_context",
                      "mycroft.skill.remove_cross_context",
                      "intent.service.skills.deactivated",
                      "intent.service.skills.activated",
                      "mycroft.skills.settings.changed",
                      "skill.converse.ping",
                      "skill.converse.request",
                      f"{test_skill_id}.activate",
                      f"{test_skill_id}.deactivate"
                      ]

    # Import and initialize installed skill
    from ovos_skill_alerts import AlertSkill
    skill = AlertSkill()

    # Specify valid languages to test
    supported_languages = ["en-us"]

    # Specify skill intents as sets
    adapt_intents = {'CreateAlarm', 'CreateOcpAlarm', 'CreateTimer', 
                     'CreateReminder', 'CreateReminderAlt', 'CreateEvent',
                     'RescheduleAlert', 'RescheduleAlertAlt', 'ListAlerts',
                     'ChangeProperties', 'ChangeMediaProperties',
                     'TimerStatus', 'CancelAlert', 'CreateList',
                     'AddListSubitems', 'QueryListNames', 'QueryTodoEntries',
                     'QueryListEntries', 'DeleteListEntries', 'DeleteList',
                     'DeleteTodoEntries', 'CalendarList'}
    padatious_intents = {'missed_alerts.intent'}

    # regex entities, not necessarily filenames
    regex = set()
    # vocab is lowercase .voc file basenames
    vocab = {'timer', 'repeat', 'next', 'everyday', 'media', 'snooze',
             'cancel', 'items', 'until', 'alert', 'list', 'stored',
             'dismiss', 'quiet', 'todo', 'playable', 'put', 'remaining', 'no',
             'weekdays', 'weekends', 'noise_words', 'remind', 'reminder', 
             'priority', 'days', 'event', 'miss', 'query', 'time', 'earlier',
             'alarm', 'create', 'and', 'delete', 'calendar', 'choice',
             'change', 'later'}
    # dialog is .dialog file basenames (case-sensitive)
    dialog = {'alert_prenotification_ask', 'list_todo_no_reminder',
              'list_alert_timeframe_intro', 'confirm_alert_playback',
              'error_no_duration', 'list_alert_none_missed',
              'list_todo_exist_confirm', 'reminder_ask_time',
              'expired_audio_alert_intro', 'list_todo_lists',
              'alarm_ocp_request', 'dav_sync_ask', 'remove_list_items_ask',
              'list_todo_no_subitems', 'confirm_cancel_all', 'confirm_cancel_timeframe',
              'timer_status_none_active', 'list_todo_subitems_added',
              'confirm_snooze_alert', 'list_todo_no_lists',
              'list_alert_wo_duration', 'in_time', 'list_todo_already_exist',
              'confirm_alert_recurring_playback', 'list_alert_w_duration',
              'confirm_cancel_alert', 'confirm_timer_started',
              'todo_item_delete_selection_intro', 'next_alert_timer',
              'error_no_time', 'repeating_every', 'list_alert_none_upcoming',
              'dav_calendar_list', 'list_alert_intro', 'confirm_todo_set',
              'next_alert', 'pick_multiple_entries',
              'alert_overlapping_duration_ask',
              'dav_inactive', 'expired_reminder', 'at_time',
              'list_todo_dont_exist', 'list_todo_reminder', 'list_deleted',
              'confirm_dismiss_alert', 'alert_expiration_past',
              'error_no_scheduled_kind', 'error_audio_reminder_too_far',
              'expired_timer', 'list_alert_missed_intro', 'alert_rescheduled',
              'confirm_alert_set', 'selection_dav_calendar',
              'error_nothing_to_cancel', 'quiet_hours_end',
              'list_todo_add_ask', 'list_todo_items_intro',
              'quiet_hours_start', 'selection_not_understood',
              'alert_overlapping_ask', 'list_item_delete_selection_intro',
              'timer_status', 'list_alert_missed', 'selection_dav_service',
              'confirm_alert_recurring', 'alarm_ask_time',
              'list_alert_timeframe_none',
              'ocp_missing', 'expired_alert', 'error_no_list_name',
              'list_todo_num_deleted', 'alert_prenotification',
              'weekday', 'alarm', 'thursday', 'until', 'sunday',
              'abbreviation_sunday', 'saturday', 'abbreviation_thursday',
              'abbreviation_saturday', 'abbreviation_friday', 'reminder',
              'timer', 'abbreviation_monday', 'monday', 'event', 'alert',
              'tuesday', 'day', 'todo', 'weekend', 'abbreviation_tuesday',
              'friday', 'abbreviation_wednesday', 'wednesday', 'once',
              'reschedule_recurring_ask'}

    @classmethod
    def setUpClass(cls) -> None:
        cls.bus.on("message", cls._on_message)
        cls.skill.config_core["secondary_langs"] = cls.supported_languages
        cls.skill._startup(cls.bus, cls.test_skill_id)
        cls.adapt_intents = {f'{cls.test_skill_id}:{intent}'
                             for intent in cls.adapt_intents}
        cls.padatious_intents = {f'{cls.test_skill_id}:{intent}'
                                 for intent in cls.padatious_intents}

    @classmethod
    def _on_message(cls, message):
        cls.messages.append(json.loads(message))

    def test_skill_setup(self):
        self.assertEqual(self.skill.skill_id, self.test_skill_id)
        for msg in self.messages:
            context = msg["context"]
            if context.get("destination") == ["gui"]:
                self.assertEqual(context["source"], self.test_skill_id)
            else:
                self.assertEqual(context["skill_id"], self.test_skill_id)

    def test_intent_registration(self):
        registered_adapt = list()
        registered_padatious = dict()
        registered_vocab = dict()
        registered_regex = dict()
        for msg in self.messages:
            if msg["type"] == "register_intent":
                registered_adapt.append(msg["data"]["name"])
            elif msg["type"] == "padatious:register_intent":
                lang = msg["data"]["lang"]
                registered_padatious.setdefault(lang, list())
                registered_padatious[lang].append(msg["data"]["name"])
            elif msg["type"] == "register_vocab":
                lang = msg["data"]["lang"]
                if msg['data'].get('regex'):
                    registered_regex.setdefault(lang, dict())
                    regex = msg["data"]["regex"].split(
                        '<', 1)[1].split('>', 1)[0].replace(
                        self.test_skill_id.replace('.', '_'), '').lower()
                    registered_regex[lang].setdefault(regex, list())
                    registered_regex[lang][regex].append(msg["data"]["regex"])
                else:
                    registered_vocab.setdefault(lang, dict())
                    voc_filename = msg["data"]["entity_type"].replace(
                        self.test_skill_id.replace('.', '_'), '').lower()
                    registered_vocab[lang].setdefault(voc_filename, list())
                    registered_vocab[lang][voc_filename].append(
                        msg["data"]["entity_value"])
        self.assertEqual(set(registered_adapt), self.adapt_intents)
        for lang in self.supported_languages:
            if self.padatious_intents:
                self.assertEqual(set(registered_padatious[lang]),
                                 self.padatious_intents)
            if self.vocab:
                self.assertEqual(set(registered_vocab[lang].keys()), self.vocab)
            if self.regex:
                self.assertEqual(set(registered_regex[lang].keys()), self.regex)
            for voc in self.vocab:
                # Ensure every vocab file has at least one entry
                self.assertGreater(len(registered_vocab[lang][voc]), 0)
            for rx in self.regex:
                # Ensure every vocab file has exactly one entry
                self.assertTrue(all((rx in line for line in
                                     registered_regex[lang][rx])))

    def test_skill_events(self):
        events = self.default_events + list(self.adapt_intents)
        for event in events:
            self.assertIn(event, [e[0] for e in self.skill.events])

    def test_dialog_files(self):
        for lang in self.supported_languages:
            for dialog in self.dialog:
                file = self.skill.find_resource(f"{dialog}.dialog", "dialog",
                                                lang)
                self.assertTrue(isfile(file), file)


@unittest.skip('Work in progress')
class TestSkillIntentMatching(unittest.TestCase):
    # Import and initialize installed skill
    from ovos_skill_alerts import AlertSkill
    skill = AlertSkill()

    import yaml
    test_intents = join(dirname(__file__), 'test_intents.yaml')
    with open(test_intents) as f:
        valid_intents = yaml.safe_load(f)

    from ovos_core.intent_services import IntentService
    bus = FakeBus()
    intent_service = IntentService  (bus)
    test_skill_id = 'test_skill.test'

    @classmethod
    def setUpClass(cls) -> None:
        cls.skill.config_core["secondary_langs"] = list(cls.valid_intents.keys())
        cls.skill._startup(cls.bus, cls.test_skill_id)
        # prevent convo
        cls.skill.speak = Mock()
        cls.skill.speak_dialog = Mock()
        cls.skill.ask_yesno = Mock()
        cls.skill.get_response = Mock()
        cls.skill.ask_selection = Mock()
        cls.skill._get_response_cascade = Mock()
        cls.skill.ask_for_prenotification = Mock()

    def test_intents(self):
        for lang in self.valid_intents.keys():
            for intent, examples in self.valid_intents[lang].items():
                intent_event = f'{self.test_skill_id}:{intent}'
                self.skill.events.remove(intent_event)
                intent_handler = Mock()
                self.skill.events.add(intent_event, intent_handler)
                for utt in examples:
                    if isinstance(utt, dict):
                        data = list(utt.values())[0]
                        utt = list(utt.keys())[0]
                    else:
                        data = list()
                    message = Message('test_utterance',
                                      {"utterances": [utt], "lang": lang})
                    self.intent_service.handle_utterance(message)
                    assert intent_handler.called, utt
                    intent_message = intent_handler.call_args[0][0]
                    self.assertIsInstance(intent_message, Message)
                    self.assertEqual(intent_message.msg_type, intent_event)
                    for datum in data:
                        if isinstance(datum, dict):
                            name = list(datum.keys())[0]
                            value = list(datum.values())[0]
                        else:
                            name = datum
                            value = None
                        if name in intent_message.data:
                            # This is an entity
                            voc_id = name
                        else:
                            # We mocked the handler, data is munged
                            voc_id = f'{self.test_skill_id.replace(".", "_")}' \
                                     f'{name}'
                        self.assertIsInstance(intent_message.data.get(voc_id),
                                              str, intent_message.data)
                        if value:
                            self.assertEqual(intent_message.data.get(voc_id),
                                             value)
                    intent_handler.reset_mock()


class FakeCalendar:
    def __init__(self):
        self.id = "testservice"
        self.name = "testcalendar"

    def save_event(a):
        pass

    def save_todo(a):
        pass

    def todos(a):
        return []

    def date_search(a):
        return []


if __name__ == "__main__":
    pytest.main()
