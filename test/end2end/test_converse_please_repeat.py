"""The converse for/else branch, against the real skill object.

``converse`` prompts with ``please_repeat`` when a reply while an alert is
active matches neither dismiss nor snooze. It called
``speak_dialog("please_repeat", listen=True)``, and ``speak_dialog`` takes
``expect_response``: it has no ``listen`` and no ``**kwargs``, so that call
raised ``TypeError`` on a real skill in every locale, and the six locale
files added for that dialog were unreachable.

Every test in ``test/test_skill.py`` replaces ``speak_dialog`` with a bare
``Mock()``, which accepts any keyword, and that whole class is skipped
besides. So the defect was invisible to the suite. This test uses the real
skill object from a MiniCroft, where ``speak_dialog`` is the real method.
"""
import datetime as dt
import os
import shutil
import tempfile
import unittest

from ovos_bus_client.message import Message
from ovoscope import get_minicroft

from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert

SKILL_ID = "ovos-skill-alerts.openvoiceos"

_MINICROFT = None
_XDG = None
_ORIGINAL_XDG = None


def setUpModule():
    global _MINICROFT, _XDG, _ORIGINAL_XDG
    _ORIGINAL_XDG = os.environ.get("XDG_DATA_HOME")
    _XDG = tempfile.mkdtemp(prefix="alerts-converse-test-xdg-")
    os.environ["XDG_DATA_HOME"] = _XDG
    _MINICROFT = get_minicroft([SKILL_ID], wait_for_trained=False, max_wait=180)


def tearDownModule():
    global _MINICROFT, _XDG, _ORIGINAL_XDG
    if _MINICROFT is not None:
        _MINICROFT.stop()
        _MINICROFT = None
    if _ORIGINAL_XDG is None:
        os.environ.pop("XDG_DATA_HOME", None)
    else:
        os.environ["XDG_DATA_HOME"] = _ORIGINAL_XDG
    if _XDG is not None:
        shutil.rmtree(_XDG, ignore_errors=True)
        _XDG = None


class TestConversePleaseRepeat(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.skill = _MINICROFT.plugin_skills[SKILL_ID].instance

    def _with_active_alarm(self):
        manager = self.skill.alert_manager
        alarm = Alert.create(
            expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30),
            alert_type=AlertType.ALARM)
        manager._active_alerts = {alarm.ident: alarm}
        return manager

    def test_an_unrecognised_reply_prompts_instead_of_raising(self):
        """The branch runs, and the prompt reaches the bus.

        Before the fix this raised TypeError inside converse, so nothing
        was spoken and the six please_repeat locale files were dead.
        """
        manager = self._with_active_alarm()
        spoken = []
        self.skill.bus.on("speak", lambda m: spoken.append(m))
        try:
            # Matches neither "dismiss" nor "snooze", so the for loop
            # falls through to its else.
            self.skill.converse(
                Message("test", {"utterances": ["purple monkey dishwasher"]}))
        finally:
            manager._active_alerts = {}

        self.assertTrue(
            spoken,
            "converse spoke nothing: the please_repeat prompt never reached "
            "the bus")

        # A non-empty speak list passes for any dialog the branch reaches,
        # so the spoken sentence is compared against the rendered
        # please_repeat line. The renderer rewrites a template, so the
        # expected set is the expansion of the file and not the file.
        said = spoken[0].data.get("utterance", "")
        self.assertIn(
            said, self._rendered("please_repeat"),
            "converse spoke %r, which is not the please_repeat line" % said)

    @staticmethod
    def _rendered(dialog):
        """Every sentence the en-US file for `dialog` can render as."""
        from ovos_spec_tools import expand
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
            "locale", "en-US", "dialog", dialog + ".dialog")
        lines = [line.strip() for line in open(path, encoding="utf-8")
                 if line.strip() and not line.strip().startswith("#")]
        assert lines, "%s is empty" % path
        out = set()
        for line in lines:
            out.update(expand(line))
        return out

    def test_speak_dialog_accepts_the_keyword_converse_uses(self):
        """The signature, read off the real method rather than a Mock.

        This is the check the unit suite could not make: its speak_dialog
        is a Mock, so `listen=True` bound there and raised only in
        production.
        """
        import inspect
        signature = inspect.signature(type(self.skill).speak_dialog)
        self.assertNotIn(
            "listen", signature.parameters,
            "speak_dialog grew a 'listen' parameter; the caller in "
            "__init__.py may be able to use it again")
        self.assertIn("expect_response", signature.parameters)
