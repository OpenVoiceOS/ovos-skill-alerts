"""Which intent owns the phrasings about an existing alarm's sound or time."""
import pytest

from test_known_intent_ties import build_container


@pytest.fixture(scope="module")
def container():
    return build_container("en-US")


@pytest.mark.parametrize("utterance, intent", [
    ("change my alarm to 8", "reschedule_alert"),
    ("change my alarm to 8 am", "reschedule_alert"),
    ("change my alarm sound to the radio", "change_media_properties"),
    ("change my alarm to play the radio", "change_media_properties"),
    ("change my alarm to a recording", "change_media_properties"),
    ("set my alarm to play a podcast", "change_media_properties"),
    ("make my alarm play music", "change_media_properties"),
    ("set my alarm with music", "change_media_properties"),
    ("set an alarm that plays music", "create_alarm"),
    ("set an alarm with the news at 7", "create_alarm"),
])
def test_phrasing_goes_to_its_owner(container, utterance, intent):
    assert container.calc_intent(utterance)["name"] == intent
