"""The numbers that the skill speaks, read off the speak messages of a real skill.

The expected words come from the grammar of each language, not from a number
writer: the ordinal names three unnamed timers, and the cardinal counts one
deleted entry, in the gender of the noun that the dialog counts.
"""
import datetime as dt
import os
import re
import shutil
import tempfile
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import get_minicroft

from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.locale import spoken_alert_type

SKILL_ID = "ovos-skill-alerts.openvoiceos"
PIPELINE = ["ovos-m2v-pipeline-high", "ovos-m2v-pipeline-medium"]

# lang: (ordinals 1-3 for "timer", cardinal 1 for the deleted entries)
EXPECTED = {
    "pt-PT": (("primeiro", "segundo", "terceiro"), "um"),     # itens (m)
    "pt-BR": (("primeiro", "segundo", "terceiro"), "um"),     # itens (m)
    "es-ES": (("primero", "segundo", "tercero"), "una"),      # tareas (f)
    "fr-FR": (("premier", "deuxième", "troisième"), "une"),   # tâches (f)
    "it-IT": (("primo", "secondo", "terzo"), "una"),          # cose (f)
    "de-DE": (("erste", "zweite", "dritte"), "ein"),          # Einträge (m)
    "nl-NL": (("eerste", "tweede", "derde"), "één"),
    "da-DK": (("første", "anden", "tredje"), "et"),           # elementer (n)
    "en-US": (("first", "second", "third"), "one"),
}



def _words(sentence):
    return re.findall(r"\w+", sentence.lower())


_MINICROFT = None
_XDG = None
_ORIGINAL_XDG = None


def setUpModule():
    global _MINICROFT, _XDG, _ORIGINAL_XDG
    _ORIGINAL_XDG = os.environ.get("XDG_DATA_HOME")
    _XDG = tempfile.mkdtemp(prefix="alerts-spoken-numbers-xdg-")
    os.environ["XDG_DATA_HOME"] = _XDG
    _MINICROFT = get_minicroft([SKILL_ID], default_pipeline=PIPELINE,
                               wait_for_trained=False, max_wait=180)


def tearDownModule():
    if _MINICROFT is not None:
        _MINICROFT.stop()
    if _ORIGINAL_XDG is None:
        os.environ.pop("XDG_DATA_HOME", None)
    else:
        os.environ["XDG_DATA_HOME"] = _ORIGINAL_XDG
    shutil.rmtree(_XDG, ignore_errors=True)


class TestSpokenNumbers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.skill = _MINICROFT.plugin_skills[SKILL_ID].instance

    def setUp(self):
        self.spoken = []
        speak = type(self.skill).speak

        def record(utterance, expect_response=False, wait=False, meta=None):
            self.spoken.append(utterance)
            return speak(self.skill, utterance, expect_response, False, meta)

        self.skill.speak = record
        self.addCleanup(delattr, self.skill, "speak")

    def _reset(self):
        manager = self.skill.alert_manager
        for ident in list(manager.pending_alerts):
            manager.rm_alert(ident)
        self.spoken.clear()

    @staticmethod
    def _message(lang, **data):
        session = Session("spoken-numbers")
        session.lang = lang
        session.pipeline = PIPELINE
        return Message("test", dict(lang=lang, utterance="", **data),
                       {"session": session.serialize()})

    def _add(self, lang, alert_type, name=None, minutes=10):
        self.skill.alert_manager.add_alert(Alert.create(
            expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes),
            alert_name=name, alert_type=alert_type, lang=lang))

    def test_timer_list_ordinals(self):
        for lang, (ordinals, _) in EXPECTED.items():
            with self.subTest(lang=lang):
                self._reset()
                for minutes in (10, 20, 30):
                    # A name that holds the type word is a default name, and
                    # the skill names such timers by their ordinal.
                    self._add(lang, AlertType.TIMER, minutes=minutes,
                              name=spoken_alert_type(AlertType.TIMER, lang))
                message = self._message(lang)
                self.skill.handle_timer_status(message)
                self.assertEqual(len(self.spoken), 3, self.spoken)
                for word, said in zip(ordinals, self.spoken):
                    self.assertIn(word, _words(said), said)

    def test_delete_all_count(self):
        for lang, (_, one) in EXPECTED.items():
            with self.subTest(lang=lang):
                self._reset()
                self._add(lang, AlertType.TODO, name="leite")
                message = self._message(lang, stored=True)
                self.skill._delete_todo_entries(message)
                self.assertTrue(self.spoken)
                self.assertIn(one, _words(self.spoken[-1]), self.spoken[-1])
