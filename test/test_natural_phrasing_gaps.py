"""Regression coverage for two natural phrasings that the en-US intent
templates could not reach.

"did I miss anything" -- missed_alerts.intent's kind-noun alternation
(alarm|alarms|alert|...|timers) never included a generic "anything"/
"something", so a user asking about missed alerts in general, rather than
about a specific kind, matched no missed_alerts template.

"remind me to take out the trash every Thursday and Sunday at 7 PM" --
the recurring lines of create_reminder.intent use weekday/weekend/
morning/afternoon shapes; none reaches an explicit day-of-week list. A
template match on such a phrasing is only useful if the handler then books
the days the user named, so that test asserts the parsed alert through
build_alert_from_intent -- days, hour and minute -- and not the confidence.

The missed_alerts test loads shipped intent files into a padacioso
IntentContainer directly (no MiniCroft/skill boot needed): missed_alerts,
plus list_alerts and create_reminder, the intents that compete for "did I
miss anything". The test asserts which intent wins,
not a score.
"""
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from padacioso import IntentContainer

from ovos_skill_alerts.util import Weekdays
from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

LOCALE_INTENT_DIR = Path(__file__).parent.parent / "locale" / "en-US" / "intent"


# missed_alerts and the intents that compete with it for a generic
# "did I miss anything": list_alerts takes it when missed_alerts cannot.
TRAINED_INTENTS = ("missed_alerts",
                   "list_alerts", "create_reminder")


def _load_container() -> IntentContainer:
    container = IntentContainer()
    for name in TRAINED_INTENTS:
        lines = (LOCALE_INTENT_DIR / f"{name}.intent").read_text(encoding="utf-8").splitlines()
        container.add_intent(name, [line for line in lines
                                    if line.strip() and not line.startswith("#")])
    return container


def test_missed_alerts_generic_phrasing():
    container = _load_container()
    match = container.calc_intent("did I miss anything")
    scores = {m["name"]: m["conf"] for m in container.calc_intents("did I miss anything")}
    assert match.get("name") == "missed_alerts", (
        f"'did I miss anything' went to {match.get('name')}, not missed_alerts; "
        f"scores: {scores}"
    )


# Neither utterance appears in create_reminder.intent, and the
# second uses a clock time none of its templates carry.
DAY_OF_WEEK_CASES = [
    ("remind me to take out the trash every Thursday and Sunday at 7 PM",
     {Weekdays.THU, Weekdays.SUN}, 19, 0),
    ("remind me to call grandma every tuesday at 6 30 pm",
     {Weekdays.TUE}, 18, 30),
]


@pytest.mark.parametrize("utterance,days,hour,minute", DAY_OF_WEEK_CASES)
def test_recurring_reminder_day_of_week_outcome(utterance, days, hour, minute):
    # file-intent shaped: no adapt "repeat" tag, only the utterance
    msg = Message("intent", {"utterance": utterance, "lang": "en-US"})
    alert = build_alert_from_intent(msg)
    assert alert is not None, f"no alert parsed for {utterance!r}"
    assert set(alert.repeat_days or []) == days, (
        f"wrong/missing day recurrence for {utterance!r}: got {alert.repeat_days}")
    assert alert.expiration is not None, f"no time extracted for {utterance!r}"
    assert (alert.expiration.hour, alert.expiration.minute) == (hour, minute), (
        f"wrong time for {utterance!r}: got {alert.expiration}")
