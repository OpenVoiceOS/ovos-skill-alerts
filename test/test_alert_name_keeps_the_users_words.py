"""An alert keeps the name the user said, and still matches when asked for again.

Two halves, and both have to hold at once:

* what is stored and spoken is the user's own words -- "Åsa" is an alert named
  Åsa, not åsa and not asa;
* what is compared is folded on both sides, so asking for "åsa" or "ÅSA" still
  finds it.

Before this, ``parse_alert_name_from_message`` lowercased the slot the intent
filled and every scavenged token, which made the stored name the folded one and
hid the loss from every comparison (T-5773, the skill half of T-5676).

The names below carry a diacritic and a capital in the three locales the task
names: sv-SE Åsa, de-DE Zahnarzt, ca-ES Núria.
"""
import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts.util.locale import get_alert_dialog_data
from ovos_skill_alerts.util.parse_utils import (
    fuzzy_match,
    parse_alert_name_from_message,
)

SPOKEN = [
    ("sv-SE", "Åsa"),
    ("de-DE", "Zahnarzt"),
    ("ca-ES", "Núria"),
    ("sv-SE", "Åsa Öberg"),
]


def _message(lang, name):
    return Message("recognizer_loop:utterance",
                   {"utterance": f"cancel my alarm for {name}",
                    "list_name": name},
                   {"lang": lang})


@pytest.mark.parametrize("lang,name", SPOKEN, ids=lambda v: str(v))
def test_the_slot_keeps_the_users_words(lang, name):
    """The half the reporter saw: the name is stored as it was said."""
    assert parse_alert_name_from_message(_message(lang, name)) == name


@pytest.mark.parametrize("lang,name", SPOKEN, ids=lambda v: str(v))
def test_a_surrounding_space_is_still_stripped(lang, name):
    """Keeping the case must not stop the strip the old code also did."""
    assert parse_alert_name_from_message(_message(lang, f"  {name} ")) == name


@pytest.mark.parametrize("stored,asked", [
    ("Åsa", "åsa"),
    ("Åsa", "ÅSA"),
    ("Zahnarzt", "zahnarzt"),
    ("Núria", "núria"),
    ("Åsa Öberg", "åsa öberg"),
])
def test_a_name_matches_whatever_case_it_is_asked_for_in(stored, asked):
    """The other half: folding moved to the comparison, so lookup still works.

    rapidfuzz is case-sensitive -- this is 67 without the fold -- so this is the
    test that would have failed if the fold had simply been deleted.
    """
    assert fuzzy_match(stored, asked) == 100
    assert fuzzy_match(stored, asked, 90) is True


def test_an_unrelated_name_still_does_not_match():
    """The control: folding must not turn the matcher into a yes-to-anything."""
    assert fuzzy_match("Åsa", "tandläkare", 90) is False
    assert fuzzy_match("Zahnarzt", "Frisör", 90) is False


def test_fuzzy_match_survives_an_empty_side():
    """Neither side is guaranteed to be a string: a missing name is common."""
    assert fuzzy_match("", "åsa") == 0
    assert fuzzy_match(None, "åsa") == 0


class TestTheDefaultNameTest:
    """util/locale.py asks whether a name is the skill's own default name.

    It does that by looking for the spoken alert type inside the name, and the
    locale files give that type in lowercase. Now that the name keeps the
    user's case, the test has to fold both sides: without that, an alert the
    skill itself named "Alarm" would read as a user-given name and the dialog
    would speak the word back as if the user had chosen it.
    """

    @staticmethod
    def _alert(name):
        import datetime as dt

        from ovos_skill_alerts.util import AlertType
        from ovos_skill_alerts.util.alert import Alert

        return Alert.create(
            expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
            alert_name=name, alert_type=AlertType.ALARM, lang="en-US",
        )

    def test_a_capitalised_default_name_reads_as_the_default(self):
        data = get_alert_dialog_data(self._alert("Alarm"), "en-US")
        assert "name" in data
        assert data["name"] == "", (
            "a name that is only the spoken alert type is the skill's own "
            f"default and must not be spoken back as a user name: {data}")

    def test_a_user_name_that_carries_a_diacritic_is_kept(self):
        data = get_alert_dialog_data(self._alert("Åsa"), "en-US")
        assert data["name"] == "Åsa"
