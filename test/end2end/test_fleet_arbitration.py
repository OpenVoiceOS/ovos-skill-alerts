"""Cross-skill regression test for ovos-skill-alerts: recurring reminder
coverage and arbitration against ovos-skill-date-time.

"remind me to go to work weekday mornings at 8" matches the recurring lines
of ``locale/en-US/intent/create_reminder.intent``. Without them, a single
``remind`` keyword out of ten words falls under adapt's ``conf_low``, so under the stock pipeline (no
low-confidence tiers) nobody answers, and under broader test pipelines
ovos-skill-date-time's ``weekday.for.date`` takes the utterance.

Routing alone is not enough: the handler must strip the recurrence phrase
("weekday", "weekend", "everyday") from the text it hands to
``extract_datetime()``. A file intent does not carry adapt's keyword tags,
so ``_strip_voc_phrase()`` in ``util/parse_utils.py`` does that on the
``voc_match()`` path.

This module asserts the PARSED OUTCOME (alert time and weekday recurrence
via ``build_alert_from_intent``) and the arbitration against date-time with
both skills loaded, on the stock pipeline order with padacioso serving the
file-intent stage.
"""
import time
import unittest

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_utils.log import LOG
from ovoscope import get_minicroft, is_pipeline_available

from ._wait_trained import wait_for_minicroft_ready
from ovos_skill_alerts.util.parse_utils import build_alert_from_intent
from ovos_skill_alerts.util import Weekdays

ALERTS_ID = "ovos-skill-alerts.openvoiceos"
DATE_TIME_ID = "ovos-skill-date-time.openvoiceos"
ENTRY_TOPIC = "recognizer_loop:utterance"
EOF_TYPES = {"ovos.utterance.handled", "mycroft.skill.handler.complete",
             "complete_intent_failure", "ovos.intent.unmatched"}

# The subset of the stock pipeline in ovos-config's mycroft.conf that serves
# these two skills, with padacioso in the file-intent slot. OCP and m2v
# stages are left out: neither skill registers OCP intents, and the m2v
# golden runner covers that engine. What this list keeps from the stock
# order is the absence of low-confidence file-intent and adapt tiers.
REAL_DEFAULT_PIPELINE = [
    "ovos-stop-pipeline-plugin-high",
    "ovos-converse-pipeline-plugin",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-high",
    "ovos-fallback-pipeline-plugin-high",
    "ovos-stop-pipeline-plugin-medium",
    "ovos-adapt-pipeline-plugin-medium",
    "ovos-fallback-pipeline-plugin-medium",
    "ovos-fallback-pipeline-plugin-low",
]

RECURRING_UTTERANCES = [
    "remind me to go to work weekday mornings at 8",
    "remind me to go to work every weekday at 8 am",
]
SIMPLE_UTTERANCE = "remind me to buy milk"


class TestRecurringReminderOutcome(unittest.TestCase):
    """Unit-level: the handler must extract the CORRECT slots, not just
    claim the intent. Exercises build_alert_from_intent directly -- no
    MiniCroft/bus round trip needed, since alert-time extraction is a pure
    function of the Message."""

    def test_weekday_recurrence_and_time_parsed_correctly(self):
        for utterance in RECURRING_UTTERANCES:
            with self.subTest(utterance=utterance):
                msg = Message("intent", {"utterance": utterance, "lang": "en-US"})
                alert = build_alert_from_intent(msg)
                self.assertIsNotNone(alert, f"no alert parsed for {utterance!r}")
                self.assertIsNotNone(
                    alert.expiration,
                    f"no time extracted for {utterance!r}")
                self.assertEqual(
                    alert.expiration.hour, 8,
                    f"wrong hour extracted for {utterance!r}: "
                    f"got {alert.expiration} (expected 8am)")
                self.assertEqual(
                    alert.expiration.minute, 0,
                    f"wrong minute extracted for {utterance!r}: "
                    f"got {alert.expiration}")
                self.assertEqual(
                    set(alert.repeat_days or []),
                    {Weekdays.MON, Weekdays.TUE, Weekdays.WED,
                     Weekdays.THU, Weekdays.FRI},
                    f"wrong/missing weekday recurrence for {utterance!r}: "
                    f"got {alert.repeat_days}")

    def test_day_of_week_recurrence_parsed_without_adapt_tag(self):
        """An explicit day list, matched as a file intent (no adapt
        "repeat" tag), must still book those days and that time."""
        cases = [
            ("remind me to take out the trash every thursday and sunday at 7 pm",
             {Weekdays.THU, Weekdays.SUN}, 19, 0),
            ("remind me to call grandma every tuesday at 6 30 pm",
             {Weekdays.TUE}, 18, 30),
        ]
        for utterance, days, hour, minute in cases:
            with self.subTest(utterance=utterance):
                msg = Message("intent", {"utterance": utterance, "lang": "en-US"})
                alert = build_alert_from_intent(msg)
                self.assertIsNotNone(alert, f"no alert parsed for {utterance!r}")
                self.assertEqual(set(alert.repeat_days or []), days,
                                 f"wrong/missing day recurrence for {utterance!r}: "
                                 f"got {alert.repeat_days}")
                self.assertIsNotNone(alert.expiration,
                                     f"no time extracted for {utterance!r}")
                self.assertEqual((alert.expiration.hour, alert.expiration.minute),
                                 (hour, minute),
                                 f"wrong time for {utterance!r}: got {alert.expiration}")

    def test_simple_one_off_reminder_unaffected(self):
        """Soundness check: a plain one-off reminder with no recurrence
        phrase must not be broken by the recurrence-stripping fix."""
        msg = Message("intent", {"utterance": SIMPLE_UTTERANCE, "lang": "en-US"})
        alert = build_alert_from_intent(msg)
        self.assertIsNotNone(alert)
        self.assertFalse(
            alert.repeat_days,
            f"simple reminder should have no recurrence, got {alert.repeat_days}")


@pytest.mark.timeout(480)
class TestReminderVsDateTimeArbitration(unittest.TestCase):
    """Two-skill MiniCroft: alerts must claim the recurring-reminder
    utterance over ovos-skill-date-time, and the handler must extract the
    correct time and weekday recurrence."""

    @classmethod
    def setUpClass(cls):
        LOG.set_level("ERROR")
        # Fail loudly on a missing test dependency instead of letting the
        # arbitration assertion below report a misleading routing failure.
        # Without padacioso installed the file-intent stage is dropped from
        # the pipeline ("Unknown pipeline matcher") and without ovos-skill-date-time there is no second
        # skill to arbitrate against; in BOTH cases the utterance simply comes
        # back as ovos.intent.unmatched, which looks exactly like a routing
        # regression. Both are declared in the `test` extra (setup.py).
        assert is_pipeline_available(REAL_DEFAULT_PIPELINE), (
            f"missing pipeline stage(s) for {REAL_DEFAULT_PIPELINE} -- install "
            f"the `test` extra (needs padacioso and ovos-adapt-parser)")
        cls.mc = get_minicroft([DATE_TIME_ID, ALERTS_ID], max_wait=600,
                                default_pipeline=REAL_DEFAULT_PIPELINE)
        loaded = set(cls.mc.plugin_skills)
        assert {ALERTS_ID, DATE_TIME_ID} <= loaded, (
            f"arbitration needs BOTH skills loaded, got {sorted(loaded)} -- "
            f"install the `test` extra (needs ovos-skill-date-time)")
        wait_for_minicroft_ready(cls.mc)

    @classmethod
    def tearDownClass(cls):
        if cls.mc is not None:
            cls.mc.stop()

    def _claimant(self, utterance):
        recs = []

        def _rec(serialized):
            if isinstance(serialized, Message):
                recs.append(serialized)
                return
            try:
                recs.append(Message.deserialize(serialized))
            except Exception:  # noqa: BLE001
                pass

        session = Session(f"fleet-arb-{abs(hash(utterance))}")
        session.lang = "en-US"
        msg = Message(ENTRY_TOPIC, {"utterances": [utterance], "lang": "en-US"},
                      {"session": session.serialize()})

        self.mc.bus.on("message", _rec)
        try:
            self.mc.bus.emit(msg)
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                if any(m.msg_type in EOF_TYPES for m in recs):
                    break
                time.sleep(0.05)
            time.sleep(0.4)
        finally:
            self.mc.bus.remove("message", _rec)

        types_seen = {m.msg_type for m in recs}
        if "ovos.intent.unmatched" in types_seen:
            return None, recs
        for m in recs:
            if ":" in m.msg_type:
                prefix = m.msg_type.split(":", 1)[0]
                if prefix in (ALERTS_ID, DATE_TIME_ID):
                    return prefix, recs
        return None, recs

    def test_recurring_reminder_routes_to_alerts_under_real_default_pipeline(self):
        utterance = RECURRING_UTTERANCES[0]
        claimant, recs = self._claimant(utterance)
        self.assertEqual(
            claimant, ALERTS_ID,
            f"real-default-pipeline coverage gap: {utterance!r} expected "
            f"{ALERTS_ID!r} but got {claimant!r}. "
            f"messages seen: {[m.msg_type for m in recs]}")
        claim_types = {m.msg_type for m in recs}
        self.assertIn(f"{ALERTS_ID}:create_reminder", claim_types)


if __name__ == "__main__":
    unittest.main()
