"""Regression coverage for two natural phrasings that the en-US padatious
templates could not reach.

"did I miss anything" -- missed_alerts.intent's kind-noun alternation
(alarm|alarms|alert|...|timers) never included a generic "anything"/
"something", so a user asking about missed alerts in general, rather than
about a specific kind, fell below padatious' conf_low (0.5).

"remind me to take out the trash every Thursday and Sunday at 7 PM" --
create_reminder_recurring.intent's 12 examples all use weekday/weekend/
morning/afternoon shapes; none reaches an explicit day-of-week list. A
padatious match on such a phrasing is only useful if the handler then books
the days the user named, so that test asserts the parsed alert through
build_alert_from_intent -- days, hour and minute -- and not the confidence.

The missed_alerts test trains a real padatious IntentContainer directly on
shipped intent files (no MiniCroft/skill boot needed): the files this change
touches, plus ListAlerts and CreateReminder, the intents that compete for
"did I miss anything". Without the widening, ListAlerts takes that utterance,
so the test asserts which intent wins, not a score. It does not train all of
locale/en-US/intent: that directory holds 25 files and about 11,000 expanded
samples, and training them all runs past the 420 s pytest timeout.
"""
import tempfile
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_padatious import IntentContainer

from ovos_skill_alerts.util import Weekdays
from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

LOCALE_INTENT_DIR = Path(__file__).parent.parent / "locale" / "en-US" / "intent"


# missed_alerts and the intents that compete with it for a generic
# "did I miss anything": ListAlerts takes it when missed_alerts cannot.
TRAINED_INTENTS = ("missed_alerts", "create_reminder_recurring",
                   "ListAlerts", "CreateReminder")


def _train_container() -> IntentContainer:
    container = IntentContainer(tempfile.mkdtemp())
    for name in TRAINED_INTENTS:
        intent_file = LOCALE_INTENT_DIR / f"{name}.intent"
        container.load_intent(name, str(intent_file))
    container.train()
    return container


def test_missed_alerts_generic_phrasing():
    container = _train_container()
    match = container.calc_intent("did I miss anything")
    scores = {m.name: round(m.conf, 3)
              for m in container.calc_intents("did I miss anything")}
    assert match.name == "missed_alerts", (
        f"'did I miss anything' went to {match.name} ({match.conf:.3f}), "
        f"not missed_alerts; scores: {scores}"
    )


# Neither utterance appears in create_reminder_recurring.intent, and the
# second uses a clock time none of its templates carry.
DAY_OF_WEEK_CASES = [
    ("remind me to take out the trash every Thursday and Sunday at 7 PM",
     {Weekdays.THU, Weekdays.SUN}, 19, 0),
    ("remind me to call grandma every tuesday at 6 30 pm",
     {Weekdays.TUE}, 18, 30),
]


@pytest.mark.parametrize("utterance,days,hour,minute", DAY_OF_WEEK_CASES)
def test_create_reminder_recurring_day_of_week_outcome(utterance, days, hour, minute):
    # padatious-shaped: no adapt "repeat" tag, only the utterance
    msg = Message("intent", {"utterance": utterance, "lang": "en-US"})
    alert = build_alert_from_intent(msg)
    assert alert is not None, f"no alert parsed for {utterance!r}"
    assert set(alert.repeat_days or []) == days, (
        f"wrong/missing day recurrence for {utterance!r}: got {alert.repeat_days}")
    assert alert.expiration is not None, f"no time extracted for {utterance!r}"
    assert (alert.expiration.hour, alert.expiration.minute) == (hour, minute), (
        f"wrong time for {utterance!r}: got {alert.expiration}")
