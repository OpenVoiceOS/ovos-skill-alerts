"""Regression coverage for two natural phrasings that the en-US padatious
templates could not reach.

"did I miss anything" -- missed_alerts.intent's kind-noun alternation
(alarm|alarms|alert|...|timers) never included a generic "anything"/
"something", so a user asking about missed alerts in general, rather than
about a specific kind, fell below padatious' conf_low (0.5).

"remind me to take out the trash every Thursday and Sunday at 7 PM" --
create_reminder_recurring.intent's 12 examples all use weekday/weekend/
morning/afternoon shapes; none reaches an explicit day-of-week list, so a
recurring reminder phrased by day name also fell below conf_low.

This test trains a real padatious IntentContainer directly on the shipped
locale/en-US/intent files (no MiniCroft/skill boot needed) and asserts both
utterances now clear conf_low.
"""
import tempfile
from pathlib import Path

from ovos_padatious import IntentContainer

LOCALE_INTENT_DIR = Path(__file__).parent.parent / "locale" / "en-US" / "intent"
CONF_LOW = 0.5


def _train_container() -> IntentContainer:
    container = IntentContainer(tempfile.mkdtemp())
    for intent_file in LOCALE_INTENT_DIR.glob("*.intent"):
        container.load_intent(intent_file.stem, str(intent_file))
    container.train()
    return container


def test_missed_alerts_generic_phrasing():
    container = _train_container()
    match = container.calc_intent("did I miss anything")
    assert match.name == "missed_alerts"
    assert match.conf >= CONF_LOW, (
        f"'did I miss anything' scored {match.conf} for missed_alerts, "
        f"below conf_low ({CONF_LOW})"
    )


def test_create_reminder_recurring_day_of_week_phrasing():
    container = _train_container()
    utterance = "remind me to take out the trash every Thursday and Sunday at 7 PM"
    match = container.calc_intent(utterance)
    assert match.name == "create_reminder_recurring"
    assert match.conf >= CONF_LOW, (
        f"{utterance!r} scored {match.conf} for create_reminder_recurring, "
        f"below conf_low ({CONF_LOW})"
    )
