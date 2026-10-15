"""The new expiration handle_reschedule_alert gives the alert.

A time of day lands on the alert's own day, so "move the baseball event to
08:00 pm" keeps an event two days out on its day. A phrase that names
today, such as "tonight at 11:30 pm", is read from now. Before this, the
handler anchored only repeating alerts on their day and read every other
time of day from now.
"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ovos_bus_client.message import Message
from ovos_config.locale import get_default_tz

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert


def _days_ahead(days, hour, minute=0):
    now = dt.datetime.now(get_default_tz())
    return (now + dt.timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0)


def _rescheduled_to(utterance, expiration):
    alert = Alert.create(expiration=expiration, alert_name="baseball",
                         alert_type=AlertType.EVENT)
    skill = SimpleNamespace(
        lang="en-US",
        _resolve_requested_alert=Mock(return_value=alert),
        alert_manager=SimpleNamespace(reschedule_alert=Mock(return_value=alert)),
        _display_alert=Mock(), speak_dialog=Mock(), ask_yesno=Mock(),
        ask_for_prenotification=Mock())
    AlertSkill.handle_reschedule_alert(skill, Message(
        "reschedule_alert.intent",
        {"utterance": utterance, "event": "event", "lang": "en-US"},
        {"lang": "en-US"}))
    skill.alert_manager.reschedule_alert.assert_called_once()
    return skill.alert_manager.reschedule_alert.call_args[0][1]


def test_a_time_of_day_keeps_the_event_on_its_day():
    assert _rescheduled_to("move the baseball event to 08:00 pm",
                           _days_ahead(2, 18)) == _days_ahead(2, 20)


def test_tonight_moves_the_event_to_today():
    if dt.datetime.now(get_default_tz()).hour >= 23:
        pytest.skip("the named time of today has already gone by")
    assert _rescheduled_to("move the baseball event to tonight at 11:30 pm",
                           _days_ahead(2, 18)) == _days_ahead(0, 23, 30)
