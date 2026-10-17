"""change_media_properties answers a user who has no alert to change."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill


@pytest.mark.parametrize("utterance", [
    "set my alarm to play music",
    "change my alarm to play music",
    "change my next timer to play the radio",
])
def test_no_alert_to_change_is_spoken_not_raised(utterance):
    skill = SimpleNamespace(
        lang="en-US",
        _resolve_requested_alert=Mock(return_value=None),
        speak_dialog=Mock())
    AlertSkill.handle_change_media_properties(skill, Message(
        "change_media_properties.intent",
        {"utterance": utterance, "alarm": "alarm", "mediakind": "music",
         "lang": "en-US"},
        {"lang": "en-US"}))
    skill.speak_dialog.assert_called_once()
    assert skill.speak_dialog.call_args[0][0] == "error_no_scheduled_kind"
