"""Gate-evidence tests for the Class C fold (refactor/unify-timeframe-and-media-alarm).

Runs the same padacioso MiniCroft engine as test_intents_en_us.py, but
asserts BEHAVIOUR (spoken dialog content, stored alert media kind) rather
than just intent-name routing:

* the timeframe-query path ("are there any alerts between 4 pm and 5 pm")
  answers with only the alert inside the window
* the plain-list path ("list my alarms") still lists
* the media-alarm path ("set an alarm with music at 7 am") stores the
  media kind; the plain path ("set an alarm at 7 am") does not

These are the timeframe-listing fold (into list_alerts) and
the media-alarm fold (into create_alarm) before/after gate.
"""
import datetime as dt
import os
import shutil
import tempfile
import unittest
from unittest import TestCase
from unittest.mock import Mock

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_config.locale import get_default_tz
from ovoscope import CaptureSession, get_minicroft, LEAN_DEFAULT_PIPELINE

from ovos_skill_alerts.util import AlertState, AlertType
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.parse_utils import parse_timeframe_from_message

from ._wait_trained import wait_for_minicroft_ready


def _clock_words(moment: dt.datetime) -> str:
    """Say a whole hour the way a person does: 8 pm, 1 am."""
    hour = moment.hour % 12 or 12
    return f"{hour} {'am' if moment.hour < 12 else 'pm'}"


def _future_window(now: dt.datetime) -> tuple:
    """A one-hour window that is always ahead of `now`, and says so in words.

    Three hours ahead, on the hour. Midnight is stepped around: the parser
    reads "12 am" as today's midnight, which is behind every caller, and reads
    it as an end at 23:59:59, so a window that names midnight would not be the
    window the skill resolves. Both are parser defects of their own; this test
    is about the timeframe query, so it asks a question the parser answers.
    Measured over all 24 hours and four minute offsets each: the resolved
    window equals this one, and is in the future, at every position.
    """
    start = (now + dt.timedelta(hours=3)).replace(
        minute=0, second=0, microsecond=0)
    if not 1 <= start.hour <= 21:
        start = (now + dt.timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0)
    return start, start + dt.timedelta(hours=1)


SKILL_ID = "ovos-skill-alerts.openvoiceos"
LANG = "en-US"

PADACIOSO_TEST_PIPELINE = [stage for stage in LEAN_DEFAULT_PIPELINE
                          if "padatious" not in stage] + [
    "ovos-padacioso-pipeline-plugin-low",
]


class TestClassCFoldGate(TestCase):
    """One MiniCroft per class -- this file runs a handful of tests, not
    thirty, so the per-class boot cost (~ a few seconds) is fine here and
    keeps store isolation trivial (fresh XDG_DATA_HOME per class)."""

    @classmethod
    def setUpClass(cls):
        cls._orig_xdg = os.environ.get("XDG_DATA_HOME")
        cls._xdg = tempfile.mkdtemp(prefix="ovos-skill-alerts-class-c-gate-")
        os.environ["XDG_DATA_HOME"] = cls._xdg
        cls.minicroft = get_minicroft([SKILL_ID],
                                      default_pipeline=PADACIOSO_TEST_PIPELINE,
                                      wait_for_trained=False)
        wait_for_minicroft_ready(cls.minicroft)
        cls.skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        # avoid real OCP bus round trips for the media-alarm path
        cls.skill.bus.wait_for_response = Mock(
            return_value=Message("ovos.common_play.pong"))
        cls.skill._ocp_query = Mock(return_value={"uri": "fake://music"})

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()
        if cls._orig_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = cls._orig_xdg
        shutil.rmtree(cls._xdg, ignore_errors=True)

    def _clear_alerts(self):
        # AlertManager keeps pending alerts in an in-memory dict fed from,
        # but independent of, the on-disk JsonStorage -- clearing the store
        # file alone leaves already-loaded alerts in memory and leaks them
        # into the next test. Remove them through the real API instead.
        manager = self.skill.alert_manager
        for alert_id in list(manager._pending_alerts):
            manager.rm_alert(alert_id, disposition=AlertState.PENDING)
        manager._alerts_store.clear()
        manager._alerts_store.store()

    def setUp(self):
        self._clear_alerts()

    def tearDown(self):
        self._clear_alerts()

    def _fire(self, utterance: str, timeout=30):
        session = Session(f"e2e-classc-{hash(utterance)}")
        session.lang = LANG
        session.pipeline = PADACIOSO_TEST_PIPELINE
        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": LANG},
            {"session": session.serialize()},
        )
        capture = CaptureSession(self.minicroft)
        capture.capture(message, timeout=timeout)
        return capture.finish()

    def _speak_dialogs(self, messages):
        """Return (dialog_name, dialog_data, utterance_text) for every
        ``ovos.utterance.speak`` message -- ``speak_dialog`` calls carry the
        rendered dialog name/data in ``meta``, ``speak`` calls (used for the
        alert-by-alert lines in ``handle_list_all_alerts``) only carry the
        already-rendered ``utterance`` text.
        """
        out = []
        for m in messages:
            if m.msg_type == "ovos.utterance.speak":
                meta = m.data.get("meta", {})
                out.append((meta.get("dialog"), meta.get("data", {}),
                           m.data.get("utterance", "")))
        return out

    # -- timeframe path (folded into list_alerts) --

    def test_timeframe_query_names_only_the_alert_inside_the_window(self):
        # The window is built from the clock, not written into the utterance,
        # and it is always in the future. "between 4 pm and 5 pm" named a
        # window that lapses every afternoon: once the clock passes it, an
        # alert inside it has lapsed too, Alert.expiration answers None, and
        # the answer can only be "nothing stored" (before T-6164 it was worse
        # than that -- the query raised TypeError and the skill spoke
        # skill.error). A window three hours ahead cannot lapse while the
        # test runs, whatever hour the test runs at.
        tz = get_default_tz()
        now = dt.datetime.now(tz)
        window_start, window_end = _future_window(now)
        utterance = (f"are there any alerts between {_clock_words(window_start)}"
                     f" and {_clock_words(window_end)}")

        # The window the skill resolves is the window this test believes in.
        # Asserted here, so a parser change shows up as a named mismatch
        # rather than as a silent "nothing stored".
        begin, end = parse_timeframe_from_message(
            Message("intent", {"utterance": utterance, "lang": LANG}, {}),
            timezone=tz)
        self.assertEqual((begin, end), (window_start, window_end),
                         f"the skill resolves {utterance!r} to "
                         f"{begin}..{end}, not {window_start}..{window_end}")

        # a name containing the alert-kind word ("alarm"/"alert"/"event") is
        # treated as generic/default and blanked out of the dialog data --
        # use names that aren't, so they show up in the spoken answer.
        inside = Alert.create(expiration=window_start + dt.timedelta(minutes=15),
                              until=window_start + dt.timedelta(minutes=45),
                              alert_name="dentist checkup",
                              alert_type=AlertType.EVENT)
        outside = Alert.create(expiration=window_end + dt.timedelta(hours=2),
                               until=window_end + dt.timedelta(hours=3),
                               alert_name="grocery run",
                               alert_type=AlertType.EVENT)
        self.skill.alert_manager.add_alert(inside)
        self.skill.alert_manager.add_alert(outside)

        messages = self._fire(utterance)
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:list_alerts", types,
                      f"did not route to list_alerts.intent: {types}")

        speaks = self._speak_dialogs(messages)
        self.assertTrue(speaks, f"no spoken dialog: {types}")
        spoken_text = " ".join(f"{d} {u}" for _, d, u in speaks)
        self.assertIn("dentist checkup", spoken_text,
                      f"expected the in-window alert named, got: {speaks}")
        self.assertNotIn("grocery run", spoken_text,
                         f"outside-of-window alert leaked into the answer: {speaks}")

    def test_a_lapsed_alert_does_not_break_a_timeframe_query(self):
        """T-6164: one lapsed pending alert used to raise TypeError.

        Alert.expiration answers None once an alert is past with no repeat
        left, and alert_time_in_range compared that None. The user heard
        skill.error for every timeframe question while such an alert sat in
        the store. The control is in the same run: the live alert is still
        named, so the query really ran.
        """
        tz = get_default_tz()
        now = dt.datetime.now(tz)
        lapsed = Alert.create(expiration=now - dt.timedelta(minutes=5),
                              until=now + dt.timedelta(minutes=25),
                              alert_name="dentist checkup",
                              alert_type=AlertType.EVENT)
        self.assertIsNone(lapsed.expiration,
                          "fixture is wrong: this alert has not lapsed")
        window_start, window_end = _future_window(now)
        live = Alert.create(expiration=window_start + dt.timedelta(minutes=15),
                            until=window_start + dt.timedelta(minutes=45),
                            alert_name="grocery run",
                            alert_type=AlertType.EVENT)
        self.skill.alert_manager.add_alert(lapsed)
        self.skill.alert_manager.add_alert(live)

        utterance = (f"are there any alerts between {_clock_words(window_start)}"
                     f" and {_clock_words(window_end)}")
        messages = self._fire(utterance)
        types = [m.msg_type for m in messages]
        self.assertNotIn("mycroft.skill.handler.error", types,
                         f"the timeframe query raised: {types}")
        speaks = self._speak_dialogs(messages)
        spoken_text = " ".join(f"{d} {u}" for _, d, u in speaks)
        self.assertNotIn("skill.error", spoken_text,
                         f"the skill spoke an error: {speaks}")
        self.assertIn("grocery run", spoken_text,
                      f"the live alert was not named: {speaks}")

    def test_plain_list_alarms_still_lists(self):
        now = dt.datetime.now(get_default_tz()) + dt.timedelta(hours=2)
        # a name containing the alert-kind word ("alarm") is treated as a
        # generic/default name and gets blanked out of the dialog data --
        # use a name that isn't, so it shows up in the spoken listing.
        alarm = Alert.create(expiration=now, alert_name="wake up call",
                             alert_type=AlertType.ALARM)
        self.skill.alert_manager.add_alert(alarm)

        messages = self._fire("list my alarms")
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:list_alerts", types,
                      f"did not route to list_alerts.intent: {types}")
        speaks = self._speak_dialogs(messages)
        spoken_text = " ".join(f"{d} {u}" for _, d, u in speaks)
        self.assertIn("wake up call", spoken_text,
                      f"plain listing did not name the alarm: {speaks}")

    # -- media-alarm path (folded into create_alarm) --

    def test_media_alarm_stores_media_kind(self):
        messages = self._fire("set an alarm with music at 7 am")
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:create_alarm", types,
                      f"did not route to create_alarm.intent: {types}")

        alerts = list(self.skill.alert_manager._pending_alerts.values())
        self.assertEqual(len(alerts), 1, f"expected exactly one stored alert: {alerts}")
        self.assertEqual(alerts[0].media_type, "ocp",
                         "media alarm did not store an ocp media kind")

    def test_plain_alarm_stores_no_media_kind(self):
        messages = self._fire("set an alarm at 7 am")
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:create_alarm", types,
                      f"did not route to create_alarm.intent: {types}")

        alerts = list(self.skill.alert_manager._pending_alerts.values())
        self.assertEqual(len(alerts), 1,
                         f"expected exactly one stored alert: "
                         f"{[(a.alert_name, a.expiration, a.media_type) for a in alerts]}")
        self.assertIsNone(alerts[0].media_type,
                          "plain alarm request stored a media kind")


if __name__ == "__main__":
    unittest.main()
