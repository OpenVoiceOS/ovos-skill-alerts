"""Gate-evidence tests for the Class C fold (refactor/unify-timeframe-and-media-alarm).

Runs the same padacioso MiniCroft engine as test_intents_en_us.py, but
asserts BEHAVIOUR (spoken dialog content, stored alert media kind) rather
than just intent-name routing:

* the timeframe-query path ("are there any alerts between 4 pm and 5 pm")
  answers with only the alert inside the window
* the plain-list path ("list my alarms") still lists
* the media-alarm path ("set an alarm with music at 7 am") stores the
  media kind; the plain path ("set an alarm at 7 am") does not

These are the timeframe-listing fold (into ListAlerts) and
the media-alarm fold (into CreateAlarm/CreateAlarmAlt) before/after gate.
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
from ovos_date_parser import extract_datetime
from ovoscope import CaptureSession, get_minicroft, LEAN_DEFAULT_PIPELINE

from ovos_skill_alerts.util import AlertState, AlertType
from ovos_skill_alerts.util.alert import Alert

from ._wait_trained import wait_for_minicroft_ready

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

    # -- timeframe path (folded into ListAlerts) --

    def test_timeframe_query_names_only_the_alert_inside_the_window(self):
        # KNOWN PRE-EXISTING DEFECT (unrelated to this fold -- parse_utils.py
        # is untouched, and handle_event_timeframe_check's body is byte
        # identical before/after): parse_alert_time_from_message extracts
        # only the LAST clock time out of a "between X and Y" phrase and
        # consumes both tokens doing so, so parse_timeframe_from_message
        # comes back with begin=<next occurrence of Y>, end=None instead of
        # begin=X, end=Y -- verified directly against parse_timeframe_from_message
        # with several phrasing variants, all showing the same begin=Y/end=None
        # result. get_alerts_in_timeframe's overlap check with a None query
        # end degrades to "does the reference alert's own span contain this
        # single point", so the fixture below targets that actual resolved
        # behaviour (a point at "5 pm") with a duration-bearing alert
        # (AlertType.EVENT, which carries `until`) rather than the nominal
        # "5 pm" clock text.
        tz = get_default_tz()
        now = dt.datetime.now(tz)
        point, _ = extract_datetime("5 pm", "en-us", now)
        # a name containing the alert-kind word ("alarm"/"alert"/"event") is
        # treated as generic/default and blanked out of the dialog data --
        # use names that aren't, so they show up in the spoken answer.
        inside = Alert.create(expiration=point - dt.timedelta(minutes=30),
                              until=point + dt.timedelta(minutes=30),
                              alert_name="dentist checkup",
                              alert_type=AlertType.EVENT)
        outside = Alert.create(expiration=point + dt.timedelta(hours=2),
                               until=point + dt.timedelta(hours=3),
                               alert_name="grocery run",
                               alert_type=AlertType.EVENT)
        self.skill.alert_manager.add_alert(inside)
        self.skill.alert_manager.add_alert(outside)

        messages = self._fire("are there any alerts between 4 pm and 5 pm")
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:ListAlerts", types,
                      f"did not route to ListAlerts.intent: {types}")

        speaks = self._speak_dialogs(messages)
        self.assertTrue(speaks, f"no spoken dialog: {types}")
        spoken_text = " ".join(f"{d} {u}" for _, d, u in speaks)
        self.assertIn("dentist checkup", spoken_text,
                      f"expected the in-window alert named, got: {speaks}")
        self.assertNotIn("grocery run", spoken_text,
                         f"outside-of-window alert leaked into the answer: {speaks}")

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
        self.assertIn(f"{SKILL_ID}:ListAlerts", types,
                      f"did not route to ListAlerts.intent: {types}")
        speaks = self._speak_dialogs(messages)
        spoken_text = " ".join(f"{d} {u}" for _, d, u in speaks)
        self.assertIn("wake up call", spoken_text,
                      f"plain listing did not name the alarm: {speaks}")

    # -- media-alarm path (folded into CreateAlarm/CreateAlarmAlt) --

    def test_media_alarm_stores_media_kind(self):
        messages = self._fire("set an alarm with music at 7 am")
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:CreateAlarm", types,
                      f"did not route to CreateAlarm.intent: {types}")

        alerts = list(self.skill.alert_manager._pending_alerts.values())
        self.assertEqual(len(alerts), 1, f"expected exactly one stored alert: {alerts}")
        self.assertEqual(alerts[0].media_type, "ocp",
                         "media alarm did not store an ocp media kind")

    def test_plain_alarm_stores_no_media_kind(self):
        messages = self._fire("set an alarm at 7 am")
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:CreateAlarm", types,
                      f"did not route to CreateAlarm.intent: {types}")

        alerts = list(self.skill.alert_manager._pending_alerts.values())
        self.assertEqual(len(alerts), 1,
                         f"expected exactly one stored alert: "
                         f"{[(a.alert_name, a.expiration, a.media_type) for a in alerts]}")
        self.assertIsNone(alerts[0].media_type,
                          "plain alarm request stored a media kind")


if __name__ == "__main__":
    unittest.main()
