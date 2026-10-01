"""A skill defines each intent once.

RULES.md, "One intent, one definition": a second resource file for the same
intent, whatever its suffix (`_alt`, `_2`, `_extra`, `_alias`), is a
duplicate definition and is not allowed. The alternative phrasings go into
the one file and the handler is registered once. A handler that exists only
to forward to another handler is the same defect seen from the code side.

This skill carried `create_alarm_alt.intent` in 18 locales, registered by
`handle_create_alarm_alt`, which did nothing but call
`handle_create_alarm`. Both are gone. These tests keep them gone.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALE = ROOT / "locale"

#: the suffixes RULES.md names, plus the separator that introduces them
DUPLICATE_SUFFIX = re.compile(r"_(alt|2|extra|alias)$")


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


if __name__ == "__main__":
    unittest.main()
