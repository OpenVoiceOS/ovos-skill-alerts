"""A skill defines each intent once.

RULES.md, "One intent, one definition": a second resource file for the same
intent, whatever its suffix (`_alt`, `_2`, `_extra`, `_alias`), is a
duplicate definition and is not allowed. The alternative phrasings go into
the one file and the handler is registered once. A handler that exists only
to forward to another handler is the same defect seen from the code side.

This skill carried `create_alarm_alt.intent` in 18 locales, registered by
`handle_create_alarm_alt`, which did nothing but call
`handle_create_alarm`. Both are gone. These tests keep them gone.

It carried `create_reminder_recurring.intent` the same way, registered by
`handle_create_reminder_recurring`, whose whole body was a call to
`handle_create_reminder`. The recurring phrasings are lines of
`create_reminder.intent`, and these tests keep the second file and the
forwarding handler from coming back.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALE = ROOT / "locale"

#: the suffixes RULES.md names, plus `_recurring`, which named a second
#: file for an intent that already had one
DUPLICATE_SUFFIX = re.compile(r"_(alt|2|extra|alias|recurring)$")


class TestOneIntentOneDefinition(unittest.TestCase):

    def test_no_intent_file_carries_a_duplicate_suffix(self):
        offenders = sorted(
            str(p.relative_to(ROOT))
            for p in LOCALE.rglob("*.intent")
            if DUPLICATE_SUFFIX.search(p.stem)
        )
        self.assertEqual(offenders, [], (
            "a second .intent file for an intent that already has one is a "
            "duplicate definition; fold the lines into the existing file and "
            "register the handler once"
        ))

    def test_create_alarm_alt_is_gone_from_every_locale(self):
        """The control for the rule above: name the file this fold removed.

        The generic check would also pass on a tree that never had the file,
        so it cannot show that the fold happened. This one can.
        """
        found = sorted(
            p.parent.parent.name
            for p in LOCALE.glob("*/intent/create_alarm_alt.intent")
        )
        self.assertEqual(found, [])

    def test_every_locale_still_defines_create_alarm(self):
        """And the fold did not take the surviving file with it."""
        locales = sorted(p.name for p in LOCALE.iterdir() if p.is_dir())
        missing = [
            l for l in locales
            if (LOCALE / l / "intent").is_dir()
            and not (LOCALE / l / "intent" / "create_alarm.intent").is_file()
        ]
        self.assertEqual(missing, [])

    def test_no_forwarding_alt_handler_remains(self):
        source = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("def handle_create_alarm_alt", source)
        self.assertNotIn('@intent_handler("create_alarm_alt.intent")', source)

    def test_create_reminder_recurring_is_gone_from_every_locale(self):
        """The control for the reminder fold, named the same way."""
        found = sorted(
            p.parent.parent.name
            for p in LOCALE.glob("*/intent/create_reminder_recurring.intent")
        )
        self.assertEqual(found, [])

    def test_every_locale_still_defines_create_reminder(self):
        locales = sorted(p.name for p in LOCALE.iterdir() if p.is_dir())
        missing = [
            l for l in locales
            if (LOCALE / l / "intent").is_dir()
            and not (LOCALE / l / "intent" / "create_reminder.intent").is_file()
        ]
        self.assertEqual(missing, [])

    def test_no_forwarding_recurring_handler_remains(self):
        source = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("def handle_create_reminder_recurring", source)
        self.assertNotIn(
            '@intent_handler("create_reminder_recurring.intent")', source)


if __name__ == "__main__":
    unittest.main()
