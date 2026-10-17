"""create_alarm reaches the OCP path when the media word is plain template text.

"set a music alarm" has no ``{mediakind}`` slot, so the handler reads the
media word from the utterance.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util.media import named_media_type


def _message(utterance, **data):
    return Message("create_alarm.intent",
                   {"utterance": utterance, "lang": "en-US", **data},
                   {"lang": "en-US"})


@pytest.mark.parametrize("utterance", [
    "set a music alarm",
    "create a podcast alarm at 7 am",
    "set an audiobook alarm",
])
def test_a_media_word_in_the_utterance_makes_an_ocp_alarm(utterance):
    skill = SimpleNamespace(handle_ocp_alarm=Mock())
    AlertSkill.handle_create_alarm(skill, _message(utterance))
    skill.handle_ocp_alarm.assert_called_once()


def test_the_mediakind_slot_still_makes_an_ocp_alarm():
    skill = SimpleNamespace(handle_ocp_alarm=Mock())
    AlertSkill.handle_create_alarm(
        skill, _message("set an alarm with a podcast", mediakind="a podcast"))
    skill.handle_ocp_alarm.assert_called_once()


@pytest.mark.parametrize("utterance", [
    "set an alarm for 7 am",
    "wake me up at 6",
])
def test_a_plain_alarm_names_no_media(utterance):
    assert named_media_type(_message(utterance)) is None
