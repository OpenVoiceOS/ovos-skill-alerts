"""On padatious, the production matcher, a request for a time on another day
creates an alarm for that day and leaves the alarm on the other day alone."""
import datetime as dt
import os
import shutil
import tempfile
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft


SKILL_ID = "ovos-skill-alerts.openvoiceos"
LANG = "en-US"
PIPELINE = ["ovos-padatious-pipeline-plugin-high", "ovos-adapt-pipeline-plugin-high",
            "ovos-padatious-pipeline-plugin-medium", "ovos-adapt-pipeline-plugin-medium"]
STATION = {"title": "Radio X", "uri": "http://radio.example/x"}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class TestPadatiousAnotherDay(TestCase):

    @classmethod
    def setUpClass(cls):
        cls._orig_xdg = os.environ.get("XDG_DATA_HOME")
        cls._xdg = tempfile.mkdtemp(prefix="ovos-skill-alerts-pad-xdg-")
        os.environ["XDG_DATA_HOME"] = cls._xdg
        cls.minicroft = get_minicroft([SKILL_ID], default_pipeline=PIPELINE,
                                      lang=LANG, max_wait=300)
        cls.minicroft.bus.on(
            "ovos.common_play.ping",
            lambda m: cls.minicroft.bus.emit(m.reply("ovos.common_play.pong")))
        cls.skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        cls.skill._ocp_query = lambda message: dict(STATION)

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()
        if cls._orig_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = cls._orig_xdg
        shutil.rmtree(cls._xdg, ignore_errors=True)

    def test_a_request_for_another_day_creates_an_alarm_for_that_day(self):
        from ovos_config.locale import get_default_tz
        from ovos_skill_alerts.util import AlertType
        from ovos_skill_alerts.util.alert import Alert
        for alarm in self.skill._get_alerts_list(AlertType.ALARM):
            self.skill.alert_manager.rm_alert(alarm.ident)
        now = dt.datetime.now(get_default_tz())
        tomorrow = (now + dt.timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
        later = now + dt.timedelta(days=2)
        self.skill.alert_manager.add_alert(Alert.create(
            expiration=tomorrow, alert_name="first", alert_type=AlertType.ALARM, lang=LANG))
        utterance = f"make my alarm play jazz at 7 am on {DAYS[later.weekday()]}"
        session = Session("padatious-another-day")
        session.lang = LANG
        session.pipeline = PIPELINE
        capture = CaptureSession(self.minicroft)
        capture.capture(Message("recognizer_loop:utterance",
                                {"utterances": [utterance], "lang": LANG},
                                {"session": session.serialize()}), timeout=20)
        capture.finish()
        alarms = sorted(self.skill._get_alerts_list(AlertType.ALARM),
                        key=lambda a: a.expiration)
        self.assertEqual([a.expiration.date() for a in alarms],
                         [tomorrow.date(), later.date()])
        self.assertIsNone(alarms[0].ocp_request)
        self.assertEqual(alarms[1].ocp_request, STATION)
