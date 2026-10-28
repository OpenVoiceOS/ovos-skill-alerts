"""The vocabulary checks in the list and OCP handlers read their .voc files.

Both ``OVOSSkill.voc_match`` and the module ``voc_match`` take the utterance
first and the vocabulary name second. Calls that passed them the other way
round looked up a vocabulary named after the utterance, found none, and never
matched: "this week" listed every alert instead of the week's, "my next alarm"
on the list intent listed every alert instead of the next one, and "cancel"
while choosing alarm media searched for "cancel" as media.
"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util.locale import voc_match


def _skill(lang):
    return SimpleNamespace(
        lang=lang,
        voc_match=lambda utt, voc, lang=None: voc_match(utt, voc, lang),
        alert_manager=SimpleNamespace(get_alerts_in_timeframe=Mock(return_value=[])),
        handle_next_alert=Mock(), handle_list_all_alerts=Mock(),
        speak_dialog=Mock(), _display_alerts=Mock())


def _list(utterance, lang):
    skill = _skill(lang)
    AlertSkill.handle_event_timeframe_check(skill, Message(
        "list_alerts.intent", {"utterance": utterance, "lang": lang}, {"lang": lang}))
    return skill


def test_next_on_the_list_intent_answers_with_the_next_alert():
    skill = _list("what is my next alarm", "en-US")
    skill.handle_next_alert.assert_called_once()
    skill.handle_list_all_alerts.assert_not_called()


def test_week_selects_the_week_range():
    week = (dt.datetime(2024, 2, 5, tzinfo=dt.timezone.utc),
            dt.datetime(2024, 2, 11, 23, 59, tzinfo=dt.timezone.utc))
    with patch("ovos_skill_alerts.get_week_range", return_value=week) as get_week_range:
        skill = _list("welche wecker habe ich diese woche", "de-DE")
    get_week_range.assert_called_once()
    assert skill.alert_manager.get_alerts_in_timeframe.call_args.args[:2] == week


def test_cancel_ends_the_media_question():
    skill = SimpleNamespace(lang="en-US", bus=Mock(), speak_dialog=Mock(),
                            get_response=Mock(return_value="please cancel"))
    with patch("ovos_skill_alerts.ocp_query", return_value="a stream") as ocp_query:
        result = AlertSkill._ocp_query(skill, Message("x", {"media": "music"}))
    assert result is None
    ocp_query.assert_not_called()
