"""Which alert _resolve_requested_alert picks when the user says "next".

Adapt tagged "next" as a ``next`` flag, but a padacioso match carries only
the utterance. With several alerts of a kind pending, "reschedule the next
event two hours earlier" resolved to none of them and the skill spoke
error_no_scheduled_kind. "next" is read from the words left once the time is
parsed out, so "the baseball event to next monday" still picks by name.
"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert


def _alert(name, alert_type, hours):
    return Alert.create(
        expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours),
        alert_name=name, alert_type=alert_type)


def _resolve(utterance, alert_type, alerts):
    skill = SimpleNamespace(lang="en-US",
                            _get_alerts_list=lambda *a, **k: list(alerts),
                            _pick_one_by_name=Mock(return_value=None))
    return AlertSkill._resolve_requested_alert(skill, Message(
        "reschedule_alert.intent", {"utterance": utterance, "lang": "en-US"},
        {"lang": "en-US"}), alert_type)


@pytest.mark.parametrize("utterance, alert_type", [
    ("reschedule the next event two hours earlier", AlertType.EVENT),
    ("move the next event to 8 pm", AlertType.EVENT),
    ("postpone my next alarm by 10 minutes", AlertType.ALARM),
])
def test_next_picks_the_soonest_of_several(utterance, alert_type):
    soonest = _alert("meeting", alert_type, 3)
    later = _alert("baseball", alert_type, 30)
    assert _resolve(utterance, alert_type, [soonest, later]) is soonest


def test_next_as_part_of_the_time_does_not_pick_the_soonest():
    soonest = _alert("meeting", AlertType.EVENT, 3)
    baseball = _alert("baseball", AlertType.EVENT, 30)
    assert _resolve("move the baseball event to next monday",
                    AlertType.EVENT, [soonest, baseball]) is not soonest


def test_an_unknown_name_with_next_in_the_time_resolves_to_none():
    alerts = [_alert("meeting", AlertType.EVENT, 3),
              _alert("baseball", AlertType.EVENT, 30)]
    assert _resolve("move the zoo event to next monday",
                    AlertType.EVENT, alerts) is None
