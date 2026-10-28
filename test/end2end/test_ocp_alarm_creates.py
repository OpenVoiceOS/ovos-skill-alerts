"""Creating an alarm that plays media creates an alarm; it never attaches
media to a different, existing alarm."""
import datetime as dt
import os
import shutil
import tempfile
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft, LEAN_DEFAULT_PIPELINE

from ._wait_trained import wait_for_minicroft_ready

SKILL_ID = "ovos-skill-alerts.openvoiceos"
LANG = "en-US"
PIPELINE = [stage for stage in LEAN_DEFAULT_PIPELINE
            if "padatious" not in stage] + [
    "ovos-padacioso-pipeline-plugin-low",
]
STATION = {"title": "Radio X", "uri": "http://radio.example/x"}

_minicroft = None
_xdg = None
_orig_xdg = None


def setUpModule():
    global _minicroft, _xdg, _orig_xdg
    _orig_xdg = os.environ.get("XDG_DATA_HOME")
    _xdg = tempfile.mkdtemp(prefix="ovos-skill-alerts-ocp-xdg-")
    os.environ["XDG_DATA_HOME"] = _xdg
    _minicroft = get_minicroft([SKILL_ID], default_pipeline=PIPELINE,
                               wait_for_trained=False)
    wait_for_minicroft_ready(_minicroft)
    _minicroft.bus.on("ovos.common_play.ping",
                      lambda m: _minicroft.bus.emit(
                          m.reply("ovos.common_play.pong")))
    _minicroft.plugin_skills[SKILL_ID].instance._ocp_query = \
        lambda message: dict(STATION)


def tearDownModule():
    global _minicroft, _xdg
    if _minicroft is not None:
        _minicroft.stop()
        _minicroft = None
    if _orig_xdg is None:
        os.environ.pop("XDG_DATA_HOME", None)
    else:
        os.environ["XDG_DATA_HOME"] = _orig_xdg
    shutil.rmtree(_xdg, ignore_errors=True)


def _tomorrow_at(hour: int) -> dt.datetime:
    from ovos_config.locale import get_default_tz
    day = dt.datetime.now(get_default_tz()) + dt.timedelta(days=1)
    return day.replace(hour=hour, minute=0, second=0, microsecond=0)


class TestOcpAlarmCreates(TestCase):

    def setUp(self):
        from ovos_skill_alerts.util import AlertType
        self.skill = _minicroft.plugin_skills[SKILL_ID].instance
        for alarm in self.skill._get_alerts_list(AlertType.ALARM):
            self.skill.alert_manager.rm_alert(alarm.ident)

    def _seed_wake_up(self):
        from ovos_skill_alerts.util import AlertType
        from ovos_skill_alerts.util.alert import Alert
        self.skill.alert_manager.add_alert(
            Alert.create(expiration=_tomorrow_at(7), alert_name="wake up",
                         alert_type=AlertType.ALARM, lang=LANG))

    def _alarms(self):
        from ovos_skill_alerts.util import AlertType
        return self.skill._get_alerts_list(AlertType.ALARM)

    def _say(self, utterance: str):
        session = Session(f"e2e-ocp-alarm-{abs(hash(utterance))}")
        session.lang = LANG
        session.pipeline = PIPELINE
        capture = CaptureSession(_minicroft)
        capture.capture(Message("recognizer_loop:utterance",
                                {"utterances": [utterance], "lang": LANG},
                                {"session": session.serialize()}),
                        timeout=15)
        return [m.msg_type for m in capture.finish()]

    def test_no_time_leaves_existing_alarm_untouched_and_asks(self):
        self._seed_wake_up()
        types = self._say("set an alarm that plays music")
        self.assertIn(f"{SKILL_ID}:create_alarm", types)
        alarms = self._alarms()
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].alert_name, "wake up")
        self.assertEqual(alarms[0].expiration.hour, 7)
        self.assertIsNone(alarms[0].ocp_request)
        self.assertNotEqual(alarms[0].media_type, "ocp")
        self.assertIn("skill.converse.get_response.enable", types)

    def test_with_time_creates_the_alarm(self):
        self._seed_wake_up()
        types = self._say("set an alarm that plays music at 6 am")
        self.assertIn(f"{SKILL_ID}:create_alarm", types)
        by_hour = {a.expiration.hour: a for a in self._alarms()}
        self.assertEqual(sorted(by_hour), [6, 7])
        self.assertEqual(by_hour[6].media_type, "ocp")
        self.assertEqual(by_hour[6].ocp_request, STATION)
        self.assertIsNone(by_hour[7].ocp_request)
        self.assertIn("ovos.utterance.speak", types)

    def test_no_time_and_no_alarm_creates_nothing_and_asks(self):
        types = self._say("set an alarm that plays music")
        self.assertIn(f"{SKILL_ID}:create_alarm", types)
        self.assertEqual(self._alarms(), [])
        self.assertIn("skill.converse.get_response.enable", types)


def _day_at_seven(days_ahead: int) -> dt.datetime:
    from ovos_config.locale import get_default_tz
    day = dt.datetime.now(get_default_tz()) + dt.timedelta(days=days_ahead)
    return day.replace(hour=7, minute=0, second=0, microsecond=0)


class TestChangeMediaIntentWithATime(TestCase):
    """The change_media_properties intent is sent straight to the skill, so
    the guard is reached whatever the matcher would have routed the phrase to."""

    setUp = TestOcpAlarmCreates.setUp
    _alarms = TestOcpAlarmCreates._alarms

    def _change_media(self, **slots):
        session = Session("e2e-change-media-direct")
        session.lang = LANG
        session.pipeline = PIPELINE
        data = {"utterance": "make my alarm play " + (slots.get("mediakind")
                                                       or slots.get("mediaform")),
                "lang": LANG, "alarm": "alarm", **slots}
        capture = CaptureSession(_minicroft)
        capture.capture(Message(f"{SKILL_ID}:change_media_properties", data,
                                {"session": session.serialize()}),
                        timeout=15)
        return capture.finish()

    def _seed(self, **kwargs):
        from ovos_skill_alerts.util import AlertType
        from ovos_skill_alerts.util.alert import Alert
        alarm = Alert.create(alert_name="first", alert_type=AlertType.ALARM,
                             lang=LANG, **kwargs)
        self.skill.alert_manager.add_alert(alarm)
        return alarm

    def _sorted_alarms(self):
        return sorted(self._alarms(), key=lambda alarm: alarm.expiration)

    def test_a_request_for_another_day_creates_an_alarm_for_that_day(self):
        self._seed(expiration=_day_at_seven(1))
        later = _day_at_seven(2)
        self._change_media(mediakind=f"jazz at 7 am on {later:%A}".lower())
        alarms = self._sorted_alarms()
        self.assertEqual([a.expiration for a in alarms], [_day_at_seven(1), later])
        self.assertIsNone(alarms[0].ocp_request)
        self.assertEqual(alarms[1].ocp_request, STATION)

    def test_a_request_with_only_the_media_form_slot_creates_no_alarm(self):
        self._seed(expiration=_day_at_seven(1))
        later = _day_at_seven(2)
        messages = self._change_media(
            mediaform=f"a recording at 7 am on {later:%A}".lower())
        self.assertEqual([a.expiration for a in self._alarms()],
                         [_day_at_seven(1)])
        dialogs = [m.data.get("meta", {}).get("dialog") for m in messages
                   if m.msg_type == "ovos.utterance.speak"]
        self.assertIn("error_no_script", dialogs)

    def test_only_the_alarm_that_rings_then_is_offered_the_media(self):
        from ovos_skill_alerts.util import Weekdays
        daily = self._seed(expiration=_day_at_seven(1), repeat_days=set(Weekdays))
        other = self._seed(expiration=_day_at_seven(1) + dt.timedelta(days=1))
        later = _day_at_seven(4)
        messages = self._change_media(
            mediakind=f"jazz at 7 am on {later:%A}".lower())
        by_id = {a.ident: a for a in self._alarms()}
        self.assertEqual(set(by_id), {daily.ident, other.ident})
        self.assertEqual(by_id[daily.ident].ocp_request, STATION)
        self.assertIsNone(by_id[other.ident].ocp_request)
        self.assertNotIn("skill.converse.get_response.enable",
                         [m.msg_type for m in messages])

    def test_a_daily_alarm_gets_the_media_and_no_second_alarm_is_created(self):
        from ovos_skill_alerts.util import Weekdays
        daily = self._seed(expiration=_day_at_seven(1), repeat_days=set(Weekdays))
        later = _day_at_seven(3)
        self._change_media(mediakind=f"jazz at 7 am on {later:%A}".lower())
        self.assertEqual([a.ident for a in self._alarms()], [daily.ident])
        self.assertEqual(self._alarms()[0].ocp_request, STATION)

    def test_a_weekly_alarm_does_not_stop_a_request_for_another_weekday(self):
        from ovos_skill_alerts.util import Weekdays
        first = _day_at_seven(2)
        self._seed(expiration=first, repeat_days={Weekdays(first.weekday())})
        other = _day_at_seven(4)
        self._change_media(mediakind=f"jazz at 7 am on {other:%A}".lower())
        alarms = self._sorted_alarms()
        self.assertEqual([a.expiration for a in alarms], [first, other])
        self.assertIsNone(alarms[0].ocp_request)
        self.assertEqual(alarms[1].ocp_request, STATION)
