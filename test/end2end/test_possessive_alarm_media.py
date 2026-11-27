"""A possessive alarm request with a time creates that alarm; it never moves
the media onto a different alarm. A request with no named sound never starts
a media search."""
import datetime as dt
import os
import shutil
import tempfile
from unittest import TestCase, mock
from zoneinfo import ZoneInfo

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft, LEAN_DEFAULT_PIPELINE

from ._wait_trained import wait_for_minicroft_ready

SKILL_ID = "ovos-skill-alerts.openvoiceos"
PIPELINE = [stage for stage in LEAN_DEFAULT_PIPELINE
            if "padatious" not in stage] + [
    "ovos-padacioso-pipeline-plugin-low",
]
STATION = {"title": "Radio X", "uri": "http://radio.example/x"}


#: Every request runs in this zone, with the skill clock frozen at ANCHOR_HOUR
#: tomorrow, so an hour with no am or pm reads the same on any CI clock.
TZ_CODE = "America/Sao_Paulo"
TZ = ZoneInfo(TZ_CODE)
ANCHOR_HOUR = 10


def _tomorrow_at(hour: int, minute: int = 0) -> dt.datetime:
    day = dt.datetime.now(TZ) + dt.timedelta(days=1)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _hour(hour, anchor: dt.datetime = None) -> int:
    """The hour an alarm gets. A string is an hour spoken with no am or pm:
    chronologia ruling 17 gives the next of its two twelve-hour readings
    after the anchor."""
    if isinstance(hour, int):
        return hour
    anchor = anchor or _tomorrow_at(ANCHOR_HOUR)
    morning = int(hour) % 12
    return next((h for h in (morning, morning + 12)
                 if anchor < anchor.replace(hour=h, minute=0)),
                morning)


class _AlarmFixture:
    """Boots one MiniCroft per locale with OCP stubbed."""
    LANG: str

    @classmethod
    def setUpClass(cls):
        cls._orig_xdg = os.environ.get("XDG_DATA_HOME")
        cls._xdg = tempfile.mkdtemp(prefix="ovos-skill-alerts-poss-xdg-")
        os.environ["XDG_DATA_HOME"] = cls._xdg
        cls.minicroft = get_minicroft([SKILL_ID], default_pipeline=PIPELINE,
                                      wait_for_trained=False, lang=cls.LANG)
        wait_for_minicroft_ready(cls.minicroft)
        cls.minicroft.bus.on(
            "ovos.common_play.ping",
            lambda m: cls.minicroft.bus.emit(m.reply("ovos.common_play.pong")))
        cls.skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        cls.queries = []
        cls.skill._ocp_query = lambda message: (cls.queries.append(message)
                                                or dict(STATION))

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()
        if cls._orig_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = cls._orig_xdg
        shutil.rmtree(cls._xdg, ignore_errors=True)

    def setUp(self):
        from ovos_skill_alerts.util import AlertType
        self.queries.clear()
        for kind in (AlertType.ALARM, AlertType.REMINDER):
            for alert in self.skill._get_alerts_list(kind):
                self.skill.alert_manager.rm_alert(alert.ident)

    def _seed(self, kind, hour, name):
        from ovos_skill_alerts.util.alert import Alert
        self.skill.alert_manager.add_alert(
            Alert.create(expiration=_tomorrow_at(hour), alert_name=name,
                         alert_type=kind, lang=self.LANG))

    def _alarms(self):
        from ovos_skill_alerts.util import AlertType
        return self.skill._get_alerts_list(AlertType.ALARM)

    def _say(self, utterance: str, anchor: dt.datetime = None):
        anchor = anchor or _tomorrow_at(ANCHOR_HOUR)
        session = Session(f"e2e-poss-{abs(hash(utterance))}",
                          location_prefs={"timezone": {"code": TZ_CODE}})
        session.lang = self.LANG
        session.pipeline = PIPELINE
        capture = CaptureSession(self.minicroft)
        with mock.patch("ovos_skill_alerts.util.parse_utils.time",
                        return_value=anchor.timestamp()):
            capture.capture(Message("recognizer_loop:utterance",
                                    {"utterances": [utterance], "lang": self.LANG},
                                    {"session": session.serialize()}),
                            timeout=15)
        return [m.msg_type for m in capture.finish()]


class _PossessiveAlarmMedia(_AlarmFixture):
    """Subclasses name the phrasings of one locale."""
    WITH_TIME: str
    WITH_TIME_NO_ALARM: str
    WITH_TIME_HOUR = 6
    CREATE_VERB_NO_TIME: str
    EXTRA_WITH_TIME: tuple = ()
    TIMED: tuple = ()

    def test_with_a_time_the_alarm_is_created_beside_the_existing_one(self):
        from ovos_skill_alerts.util import AlertType
        self._seed(AlertType.ALARM, 7, "wake up")
        types = self._say(self.WITH_TIME)
        self.assertIn(f"{SKILL_ID}:create_alarm", types)
        self.assertNotIn(f"{SKILL_ID}:change_media_properties", types)
        hour = _hour(self.WITH_TIME_HOUR)
        by_hour = {a.expiration.hour: a for a in self._alarms()}
        self.assertEqual(sorted(by_hour), sorted([hour, 7]))
        self.assertEqual(by_hour[hour].ocp_request, STATION)
        self.assertIsNone(by_hour[7].ocp_request)

    def _assert_creates_the_alarm(self, utterance: str, hour):
        from ovos_skill_alerts.util import AlertType
        hour = _hour(hour)
        for alarm in self._alarms():
            self.skill.alert_manager.rm_alert(alarm.ident)
        self._seed(AlertType.ALARM, 7, "wake up")
        self._say(utterance)
        self.assertEqual(sorted(a.expiration.hour
                                for a in self._alarms()), sorted([hour, 7]))
        for alarm in self._alarms():
            self.skill.alert_manager.rm_alert(alarm.ident)
        self._say(utterance)
        self.assertEqual([a.expiration.hour for a in self._alarms()], [hour])

    def test_every_extra_phrasing_with_a_time_creates_the_alarm(self):
        for utterance, hour in self.EXTRA_WITH_TIME:
            with self.subTest(utterance=utterance):
                self._assert_creates_the_alarm(utterance, hour)

    def test_a_written_time_creates_the_alarm_with_and_without_another_alarm(self):
        from ovos_skill_alerts.util import AlertType
        for utterance, spoken in self.TIMED:
            hour = _hour(spoken)
            for seeded in (True, False):
                with self.subTest(utterance=utterance, seeded=seeded):
                    for alarm in self._alarms():
                        self.skill.alert_manager.rm_alert(alarm.ident)
                    if seeded:
                        self._seed(AlertType.ALARM, 7, "wake up")
                    types = self._say(utterance)
                    hours = sorted(a.expiration.hour for a in self._alarms())
                    self.assertEqual(hours, sorted([hour] + ([7] if seeded else [])))
                    created = [a for a in self._alarms() if a.expiration.hour == hour]
                    self.assertEqual(created[0].ocp_request, STATION)

    def test_with_a_time_and_no_alarm_the_alarm_is_created(self):
        types = self._say(self.WITH_TIME_NO_ALARM)
        self.assertIn(f"{SKILL_ID}:create_alarm", types)
        alarms = self._alarms()
        self.assertEqual([a.expiration.hour for a in alarms], [_hour(self.WITH_TIME_HOUR)])
        self.assertEqual(alarms[0].ocp_request, STATION)

    def test_a_create_verb_without_a_time_is_a_new_alarm_request(self):
        from ovos_skill_alerts.util import AlertType
        self._seed(AlertType.ALARM, 7, "wake up")
        types = self._say(self.CREATE_VERB_NO_TIME)
        self.assertIn(f"{SKILL_ID}:create_alarm", types)
        self.assertNotIn(f"{SKILL_ID}:change_media_properties", types)


class _AnotherDay:
    """A request for a time on another day creates an alarm for that day."""
    ANOTHER_DAY: str
    DAYS: tuple

    def test_a_request_for_another_day_creates_an_alarm_for_that_day(self):
        from ovos_skill_alerts.util import AlertType
        monday = _tomorrow_at(ANCHOR_HOUR) + dt.timedelta(days=1)
        utterance = self.ANOTHER_DAY.format(day=self.DAYS[monday.weekday()])
        self._seed(AlertType.ALARM, 7, "first")
        self._say(utterance)
        alarms = sorted(self._alarms(), key=lambda a: a.expiration)
        self.assertEqual([a.expiration.date() for a in alarms],
                         [(monday - dt.timedelta(days=1)).date(), monday.date()])
        self.assertIsNone(alarms[0].ocp_request)
        self.assertEqual(alarms[1].ocp_request, STATION)


class TestEnglish(_PossessiveAlarmMedia, _AnotherDay, TestCase):
    LANG = "en-US"
    WITH_TIME = "set my alarm to play music at 6 am"
    WITH_TIME_NO_ALARM = "set my alarm to play music at 6 am"
    CREATE_VERB_NO_TIME = "create my alarm with music"
    EXTRA_WITH_TIME = (("set the alarm to play music at 6 am", 6),
                       ("set the alarm to play the radio for 6 am", 6),
                       ("make my alarm play the radio for 6 am", 6))
    ANOTHER_DAY = "make my alarm play jazz at 7 am on {day}"
    DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    TIMED = (("make my alarm play the radio at 18:00 tomorrow", 18),
             ("make my alarm play the radio for 6:30 am", 6))


    def test_a_time_that_names_an_existing_alarm_changes_that_alarm(self):
        from ovos_skill_alerts.util import AlertType
        for utterance, hour in (("change my 7 am alarm to play jazz", 7),
                                ("set my 8 am alarm to play the radio", 8)):
            with self.subTest(utterance=utterance):
                for alarm in self._alarms():
                    self.skill.alert_manager.rm_alert(alarm.ident)
                self._seed(AlertType.ALARM, 7, "first")
                self._seed(AlertType.ALARM, 8, "second")
                self._say(utterance)
                by_hour = {a.expiration.hour: a for a in self._alarms()}
                self.assertEqual(sorted(a.expiration.hour for a in self._alarms()), [7, 8])
                self.assertEqual(by_hour[hour].ocp_request, STATION)
                self.assertIsNone(by_hour[15 - hour].ocp_request)


class TestDanish(_PossessiveAlarmMedia, TestCase):
    LANG = "da-DK"
    WITH_TIME = "sæt min alarm med musik klokken 6"
    WITH_TIME_NO_ALARM = "sæt min alarm med musik klokken 6"
    WITH_TIME_HOUR = "6"
    CREATE_VERB_NO_TIME = "opret min alarm med musik"


class TestPortuguese(_PossessiveAlarmMedia, _AnotherDay, TestCase):
    LANG = "pt-BR"
    WITH_TIME = "defina o alarme para tocar música às 6"
    WITH_TIME_NO_ALARM = "defina o alarme para tocar música às 6"
    WITH_TIME_HOUR = "6"
    CREATE_VERB_NO_TIME = "crie meu alarme com música"
    ANOTHER_DAY = "deixe o alarme tocar jazz às 7 de {day}"
    DAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
    TIMED = (("deixe o alarme tocar música às 6h30", 6),
             ("deixe o alarme tocar música às 6:30", "6"),
             ("deixe o alarme tocar música às 18h", 18),
             ("deixe o alarme tocar jazz às 6h", 6),
             ("deixe o alarme tocar música ao meio-dia", 12),
             ("deixe o alarme tocar música à uma", "1"))
    EXTRA_WITH_TIME = (("deixe o alarme tocar música às 6", "6"),
                       ("faça o meu alarme tocar música às 6", "6"),
                       ("defina o meu alarme para tocar música às 6", "6"),
                       ("faça o meu alarme tocar jazz às 6h30", 6))

    def test_a_written_time_with_no_am_or_pm_is_the_next_of_its_two_readings(self):
        for anchor_hour, expected in ((5, _tomorrow_at(6, 30)),
                                      (10, _tomorrow_at(18, 30)),
                                      (23, _tomorrow_at(6, 30) + dt.timedelta(days=1))):
            with self.subTest(anchor_hour=anchor_hour):
                for alarm in self._alarms():
                    self.skill.alert_manager.rm_alert(alarm.ident)
                self._say("deixe o alarme tocar música às 6:30",
                          anchor=_tomorrow_at(anchor_hour))
                self.assertEqual([a.expiration.astimezone(TZ).replace(tzinfo=None)
                                  for a in self._alarms()],
                                 [expected.replace(tzinfo=None)])

    @pytest.mark.xfail(strict=True, reason="chronologia-family:FOR-TO (TigreGotico/chronologia#1008): "
                       "chronologia reads no bare hour after 'para as'")
    def test_a_spoken_hour_after_para_creates_the_alarm(self):
        self._assert_creates_the_alarm("deixe o alarme tocar música para as 6", "6")

    def test_an_unlisted_kind_changes_the_existing_alarm(self):
        from ovos_skill_alerts.util import AlertType
        for utterance in ("deixe o alarme tocar jazz",
                          "faça meu alarme tocar rock",
                          "deixe o alarme tocar a minha playlist"):
            with self.subTest(utterance=utterance):
                for alarm in self._alarms():
                    self.skill.alert_manager.rm_alert(alarm.ident)
                self.queries.clear()
                self._seed(AlertType.ALARM, 7, "acordar")
                types = self._say(utterance)
                self.assertIn(f"{SKILL_ID}:change_media_properties", types)
                self.assertEqual(len(self.queries), 1)
                alarms = self._alarms()
                self.assertEqual([a.expiration.hour for a in alarms], [7])
                self.assertEqual(alarms[0].ocp_request, STATION)

    def test_a_phrasing_with_the_article_as_changes_the_existing_alarm(self):
        from ovos_skill_alerts.util import AlertType
        for utterance in ("mude o meu alarme para as notícias",
                          "mude o som do meu alarme para as notícias",
                          "deixe o alarme tocar as minhas músicas favoritas",
                          "defina o alarme para tocar as músicas"):
            with self.subTest(utterance=utterance):
                for alarm in self._alarms():
                    self.skill.alert_manager.rm_alert(alarm.ident)
                self.queries.clear()
                self._seed(AlertType.ALARM, 7, "acordar")
                types = self._say(utterance)
                self.assertIn(f"{SKILL_ID}:change_media_properties", types)
                self.assertNotIn(f"{SKILL_ID}:reschedule_alert", types)
                alarms = self._alarms()
                self.assertEqual([a.expiration.hour for a in alarms], [7])
                self.assertEqual(alarms[0].ocp_request, STATION)


class TestPersian(_AlarmFixture, TestCase):
    LANG = "fa-IR"

    def test_the_alarm_clock_word_is_not_a_time(self):
        from ovos_skill_alerts.util import AlertType
        self._seed(AlertType.ALARM, 7, "wake up")
        self._say("برای ساعت هشدار من یک ضبط پخش کن")
        self.assertEqual([a.expiration.hour for a in self._alarms()], [7])
