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
                   {"utterance": utterance,
                    "mediakind": "the radio", "lang": "en-US", **data},
                   {"lang": "en-US"})


def _skill(alert, ocp_result=None):
    skill = SimpleNamespace(
        lang="en-US",
        _resolve_requested_alert=Mock(return_value=alert),
        _ocp_query=Mock(return_value=ocp_result),
        bus=SimpleNamespace(wait_for_response=Mock(return_value=object())),
        alert_manager=SimpleNamespace(write_cache_now=Mock(),
                                      sync_dav_item=Mock()),
        handle_create_alarm=Mock(),
        _get_alerts_list=Mock(return_value=[]),
        speak_dialog=Mock())
    skill._alarm_rings_at = lambda when: AlertSkill._alarm_rings_at(skill, when)
    return skill


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


@pytest.mark.parametrize("utterance", [
    "change my alarm to a recording",
    "change my reminder to a recording",
    "change my alarm to an audio file",
])
def test_a_recording_is_a_file_not_a_media_search(utterance):
    alarm = _alarm_with_source()
    skill = _skill(alarm, {"title": "Radio X"})
    AlertSkill.handle_change_media_properties(
        skill, _message(utterance, mediakind=None))
    skill._ocp_query.assert_not_called()
    assert alarm.ocp_request is None
    assert skill.speak_dialog.call_args[0][0] == "error_no_script"


@pytest.mark.parametrize("utterance", [
    "read my reminder out loud when it fires",
    "read my alarm aloud when it rings",
])
def test_a_phrasing_that_names_no_sound_is_not_a_media_search(utterance):
    alarm = _alarm_with_source()
    skill = _skill(alarm, {"title": "Radio X"})
    AlertSkill.handle_change_media_properties(
        skill, _message(utterance, mediakind=None))
    skill._ocp_query.assert_not_called()
    skill.alert_manager.write_cache_now.assert_not_called()
    assert alarm.ocp_request is None
    assert skill.speak_dialog.call_args[0][0] == "error_no_script"


def test_a_media_kind_in_the_utterance_is_a_media_search():
    alarm = _alarm_with_source()
    skill = _skill(alarm, {"title": "Radio X"})
    AlertSkill.handle_change_media_properties(
        skill, _message("change my alarm to the radio", mediakind=None))
    skill._ocp_query.assert_called_once()
    assert alarm.ocp_request == {"title": "Radio X"}


@pytest.mark.parametrize("utterance, mediakind, source", [
    ("set my alarm to play a recording", "a recording", "file"),
    ("set my alarm to play an audio file", "an audio file", "file"),
    ("set my alarm to play music", "music", "ocp"),
    ("set my alarm to play the radio", "the radio", "ocp"),
    ("set my alarm to play jazz", "jazz", "ocp"),
    ("change my alarm to audio", "audio", "file"),
])
def test_the_slot_value_decides_between_a_file_and_a_search(utterance, mediakind, source):
    from ovos_skill_alerts.util.media import get_media_source_from_intent
    assert get_media_source_from_intent(_message(utterance, mediakind=mediakind)) == source


def _at_hour(hour):
    day = dt.datetime.now(get_default_tz()) + dt.timedelta(days=1)
    return day.replace(hour=hour, minute=0, second=0, microsecond=0)


@pytest.mark.parametrize("utterance, mediakind, lang, creates", [
    ("make my alarm play the radio at 6 am", "the radio at 6 am", "en-US", True),
    ("make my alarm play the radio for 6:30", "the radio for 6:30", "en-US", True),
    ("deixe o alarme tocar música às 6h30", "música às 6h30", "pt-BR", True),
    ("make my alarm play the radio for me", "the radio for me", "en-US", False),
    ("make my alarm play the radio", "the radio", "en-US", False),
    ("change my 7 am alarm to play jazz", "jazz", "en-US", False),
    ("mude o meu alarme para as 8", None, "pt-BR", False),
    ("برای ساعت هشدار من یک ضبط پخش کن", "ساعت هشدار", "fa-IR", False),
])
def test_an_alarm_request_with_a_time_in_the_media_goes_to_the_create_path(
        utterance, mediakind, lang, creates):
    alarm = _alarm_with_source()
    skill = _skill(alarm, {"title": "Radio X"})
    message = _message(utterance, mediakind=mediakind, lang=lang)
    AlertSkill.handle_change_media_properties(skill, message)
    assert skill.handle_create_alarm.called == creates
    if creates:
        skill._ocp_query.assert_not_called()


def test_a_time_that_an_existing_alarm_rings_at_changes_that_alarm():
    seven = Alert.create(expiration=_at_hour(7), alert_name="alarm",
                         alert_type=AlertType.ALARM)
    skill = _skill(seven, {"title": "Radio X"})
    skill._get_alerts_list = Mock(return_value=[seven])
    AlertSkill.handle_change_media_properties(
        skill, _message("set the alarm to play the radio at 7 am",
                        mediakind="the radio at 7 am"))
    skill.handle_create_alarm.assert_not_called()
    assert seven.ocp_request == {"title": "Radio X"}


def test_a_reminder_request_with_a_time_is_not_turned_into_an_alarm():
    reminder = Alert.create(
        expiration=dt.datetime.now(get_default_tz()) + dt.timedelta(hours=2),
        alert_name="call mom", alert_type=AlertType.REMINDER)
    skill = _skill(reminder, {"title": "Radio X"})
    message = _message("change my reminder to play the radio at 6 am")
    AlertSkill.handle_change_media_properties(skill, message)
    skill.handle_create_alarm.assert_not_called()


def test_an_alarm_on_another_day_does_not_ring_at_the_requested_time():
    saturday = Alert.create(expiration=_at_hour(7), alert_name="alarm",
                            alert_type=AlertType.ALARM)
    skill = _skill(saturday)
    skill._get_alerts_list = Mock(return_value=[saturday])
    assert AlertSkill._alarm_rings_at(skill, _at_hour(7))
    assert AlertSkill._alarm_rings_at(skill, _at_hour(7) + dt.timedelta(seconds=40))
    assert not AlertSkill._alarm_rings_at(skill, _at_hour(7) + dt.timedelta(days=2))
    assert not AlertSkill._alarm_rings_at(skill, _at_hour(8))
