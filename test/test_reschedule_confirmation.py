"""Which confirmation handle_reschedule_alert speaks for a named and a
default-named alert.

get_alert_dialog_data blanks the name of an alert whose name is its kind, such
as a timer called "timer". alert_rescheduled then spoke as "of type timer
adjusted"; the handler speaks alert_rescheduled_unnamed for such an alert.
"""
import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert


def _timer(name):
    return Alert.create(
        expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
        alert_name=name, alert_type=AlertType.TIMER)


def _reschedule(alert):
    skill = SimpleNamespace(
        lang="en-US",
        _resolve_requested_alert=Mock(return_value=alert),
        alert_manager=SimpleNamespace(reschedule_alert=Mock(return_value=alert)),
        _display_alert=Mock(), speak_dialog=Mock(), ask_yesno=Mock(),
        ask_for_prenotification=Mock())
    AlertSkill.handle_reschedule_alert(skill, Message(
        "reschedule_alert.intent",
        {"utterance": "extend the timer by 2 minutes", "lang": "en-US"}, {"lang": "en-US"}))
    skill.speak_dialog.assert_called_once()
    return skill.speak_dialog.call_args[0]


class TestRescheduleConfirmation(unittest.TestCase):
    def test_a_default_named_timer_is_confirmed_by_its_kind(self):
        dialog, data = _reschedule(_timer("timer"))
        self.assertEqual("alert_rescheduled_unnamed", dialog)
        self.assertEqual("", data["name"])

    def test_a_named_timer_is_confirmed_by_its_name(self):
        dialog, data = _reschedule(_timer("pizza"))
        self.assertEqual("alert_rescheduled", dialog)
        self.assertEqual("pizza", data["name"])
