"""get_alert_type_from_intent takes the kind from the intent, not from
message.data.

A create intent names its kind, so "remind me to wake up the kids at 7" is a
reminder although wake.voc matches it. Any other intent takes the kind from
the utterance, and the message stays as it came off the bus.
handle_list_all_alerts lists every kind when the request names none.
"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.locale import get_alert_type_from_intent

SKILL_ID = "ovos-skill-alerts.openvoiceos"


def _message(intent, utterance, lang="en-US"):
    return Message(f"{SKILL_ID}:{intent}",
                   {"utterance": utterance, "lang": lang},
                   {"lang": lang})


@pytest.mark.parametrize("intent, utterance, expected", [
    ("create_reminder", "remind me to wake up the kids at 7", AlertType.REMINDER),
    ("create_reminder.intent", "remind me to wake up the kids at 7", AlertType.REMINDER),
    ("create_timer", "set one for 10 minutes", AlertType.TIMER),
    ("create_event", "add an appointment to set my alarm", AlertType.EVENT),
    ("create_alarm", "get me up at 7", AlertType.ALARM),
])
def test_a_create_intent_names_the_kind(intent, utterance, expected):
    assert get_alert_type_from_intent(_message(intent, utterance))[0] == expected


@pytest.mark.parametrize("lang, utterance, expected", [
    ("en-US", "cancel my alarm", AlertType.ALARM),
    ("en-US", "cancel all my timers", AlertType.TIMER),
    ("en-US", "cancel my appointment", AlertType.EVENT),
    ("en-US", "cancel my reminders", AlertType.REMINDER),
    ("en-US", "cancel all my alerts", AlertType.ALL),
    ("en-US", "cancel everything", AlertType.ALL),
    ("en-US", "cancel my timer and my alarm", AlertType.ALARM),
    ("fr-FR", "annule l'alarme", AlertType.ALARM),
    ("it-IT", "annulla l'allarme", AlertType.ALARM),
    ("kab", "sefsex alarme-inu", AlertType.ALARM),
])
def test_another_intent_takes_the_kind_from_the_utterance(lang, utterance, expected):
    assert get_alert_type_from_intent(
        _message("cancel_alert", utterance, lang))[0] == expected


def test_the_message_data_is_not_changed():
    message = _message("cancel_alert", "cancel my alarm and my timer")
    before = dict(message.data)
    get_alert_type_from_intent(message)
    assert message.data == before


def test_a_list_request_that_names_no_kind_lists_every_kind():
    now = dt.datetime.now(dt.timezone.utc)
    alarm = Alert.create(expiration=now + dt.timedelta(hours=1),
                         alert_name="wake up", alert_type=AlertType.ALARM)
    timer = Alert.create(expiration=now + dt.timedelta(minutes=5),
                         alert_name="oven", alert_type=AlertType.TIMER)
    skill = SimpleNamespace(
        lang="en-US",
        _get_alerts_list=Mock(return_value=[alarm, timer]),
        _display_alerts=Mock(), speak_dialog=Mock(), speak=Mock(),
        resources=SimpleNamespace(render_dialog=Mock(return_value="at noon")))
    with patch("ovos_skill_alerts.time.sleep"):
        AlertSkill.handle_list_all_alerts(
            skill, _message("list_alerts", "what is on my schedule"))
    spoken = " ".join(call.args[0] for call in skill.speak.call_args_list)
    assert "wake up" in spoken
    assert "oven" in spoken
