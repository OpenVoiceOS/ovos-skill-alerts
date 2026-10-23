"""On the published m2v model, which has no slots, a reschedule request that
it sends to change_media_properties creates no alarm."""
import datetime as dt
import os
import shutil
import tempfile
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft
from ovoscope.golden_minicroft import warm_m2v_models

SKILL_ID = "ovos-skill-alerts.openvoiceos"
LANG = "pt-BR"
PIPELINE = ["ovos-adapt-pipeline-plugin-high", "ovos-m2v-pipeline-high",
            "ovos-adapt-pipeline-plugin-medium", "ovos-m2v-pipeline-medium"]


class TestPublishedModelReschedule(TestCase):

    @classmethod
    def setUpClass(cls):
        cls._orig_xdg = os.environ.get("XDG_DATA_HOME")
        cls._xdg = tempfile.mkdtemp(prefix="ovos-skill-alerts-m2v-xdg-")
        os.environ["XDG_DATA_HOME"] = cls._xdg
        cls.minicroft = get_minicroft([SKILL_ID], default_pipeline=PIPELINE,
                                      lang=LANG, max_wait=300)
        warm_m2v_models(cls.minicroft)
        cls.skill = cls.minicroft.plugin_skills[SKILL_ID].instance

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()
        if cls._orig_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = cls._orig_xdg
        shutil.rmtree(cls._xdg, ignore_errors=True)

    def test_mude_o_meu_alarme_para_as_8_creates_no_alarm(self):
        from ovos_config.locale import get_default_tz
        from ovos_skill_alerts.util import AlertType
        from ovos_skill_alerts.util.alert import Alert
        for alarm in self.skill._get_alerts_list(AlertType.ALARM):
            self.skill.alert_manager.rm_alert(alarm.ident)
        day = dt.datetime.now(get_default_tz()) + dt.timedelta(days=1)
        self.skill.alert_manager.add_alert(Alert.create(
            expiration=day.replace(hour=7, minute=0, second=0, microsecond=0),
            alert_name="acordar", alert_type=AlertType.ALARM, lang=LANG))
        session = Session("m2v-reschedule")
        session.lang = LANG
        session.pipeline = PIPELINE
        capture = CaptureSession(self.minicroft)
        capture.capture(Message("recognizer_loop:utterance",
                                {"utterances": ["mude o meu alarme para as 8"], "lang": LANG},
                                {"session": session.serialize()}), timeout=20)
        capture.finish()
        self.assertEqual([a.expiration.hour
                          for a in self.skill._get_alerts_list(AlertType.ALARM)], [7])
