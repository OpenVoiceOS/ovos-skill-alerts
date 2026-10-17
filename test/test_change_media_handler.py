"""change_media_properties answers whether or not the user has an alert."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ovos_bus_client.message import Message
from ovos_config.locale import get_default_tz

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert


def _message(utterance, **data):
    return Message("change_media_properties.intent",
                   {"utterance": utterance, "alarm": "alarm",
                    "mediakind": "the radio", "lang": "en-US", **data},
                   {"lang": "en-US"})


def _skill(alert, ocp_result=None):
    return SimpleNamespace(
        lang="en-US",
        _resolve_requested_alert=Mock(return_value=alert),
        _ocp_query=Mock(return_value=ocp_result),
        bus=SimpleNamespace(wait_for_response=Mock(return_value=object())),
        alert_manager=SimpleNamespace(write_cache_now=Mock(),
                                      sync_dav_item=Mock()),
        speak_dialog=Mock())


@pytest.mark.parametrize("utterance", [
    "set my alarm to play music",
    "change my alarm to play the radio",
    "change my next timer to play the news",
])
def test_no_alert_to_change_is_spoken_not_raised(utterance):
    skill = _skill(None)
    AlertSkill.handle_change_media_properties(skill, _message(utterance))
    skill.speak_dialog.assert_called_once()
    assert skill.speak_dialog.call_args[0][0] == "error_no_scheduled_kind"


@pytest.mark.parametrize("utterance", [
    "change my alarm to play the radio",
    "set my alarm to play a podcast",
])
def test_an_alarm_gets_the_media_it_was_asked_to_play(utterance):
    alarm = Alert.create(
        expiration=dt.datetime.now(get_default_tz()) + dt.timedelta(hours=2),
        alert_name="alarm", alert_type=AlertType.ALARM)
    result = {"title": "Radio X", "uri": "http://radio.example/x"}
    skill = _skill(alarm, result)
    AlertSkill.handle_change_media_properties(skill, _message(utterance))
    assert alarm.ocp_request == result
    skill.alert_manager.write_cache_now.assert_called_once()
    skill.speak_dialog.assert_called_once()
    assert skill.speak_dialog.call_args[0][0] == "media_type_set"


def test_the_alarm_keeps_its_media_when_the_search_finds_nothing():
    alarm = Alert.create(
        expiration=dt.datetime.now(get_default_tz()) + dt.timedelta(hours=2),
        alert_name="alarm", alert_type=AlertType.ALARM)
    skill = _skill(alarm, None)
    AlertSkill.handle_change_media_properties(
        skill, _message("change my alarm to play the radio"))
    assert alarm.ocp_request is None
    assert skill.speak_dialog.call_args[0][0] == "ocp_breaking_up"


def _alarm_with_source(source=None):
    alarm = Alert.create(
        expiration=dt.datetime.now(get_default_tz()) + dt.timedelta(hours=2),
        alert_name="alarm", alert_type=AlertType.ALARM)
    if source:
        alarm.ocp_request = source
    return alarm


def test_without_common_play_the_alarm_is_left_alone():
    alarm = _alarm_with_source()
    skill = _skill(alarm, {"title": "Radio X"})
    skill.bus.wait_for_response = Mock(return_value=None)
    AlertSkill.handle_change_media_properties(
        skill, _message("change my alarm to play the radio"))
    assert alarm.ocp_request is None
    skill._ocp_query.assert_not_called()
    skill.alert_manager.write_cache_now.assert_not_called()
    assert skill.speak_dialog.call_args[0][0] == "ocp_missing"


def test_the_changed_alarm_is_synced_once():
    skill = _skill(_alarm_with_source(), {"title": "Radio X"})
    AlertSkill.handle_change_media_properties(
        skill, _message("change my alarm to play the radio"))
    skill.alert_manager.sync_dav_item.assert_called_once()


def test_an_alarm_that_had_media_says_what_it_changed_from():
    alarm = _alarm_with_source({"title": "Old Song"})
    skill = _skill(alarm, {"title": "Radio X"})
    AlertSkill.handle_change_media_properties(
        skill, _message("change my alarm to play the radio"))
    assert alarm.ocp_request == {"title": "Radio X"}
    name, data = skill.speak_dialog.call_args[0]
    assert name == "media_type_changed"
    assert data == {"old": "Old Song", "new": "the radio"}
