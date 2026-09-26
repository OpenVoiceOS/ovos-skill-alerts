"""A skill defines each intent once.

RULES.md, "One intent, one definition": a second resource file for the same
intent, whatever its suffix (`_alt`, `_2`, `_extra`, `_alias`), is a
duplicate definition and is not allowed. The alternative phrasings go into
the one file and the handler is registered once. A handler that exists only
to forward to another handler is the same defect seen from the code side.

This skill carried `create_alarm_alt.intent` in 18 locales, registered by
`handle_create_alarm_alt`, which did nothing but call
`handle_create_alarm`. Both are gone. These tests keep them gone.

It carried `create_reminder_recurring.intent` in 19 locales the same way,
registered by `handle_create_reminder_recurring`, whose whole body was a
call to `handle_create_reminder`. The recurring lines are now lines of
`create_reminder.intent`, so one padatious template covers the short and
the long forms. These tests keep that file and that handler gone too.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALE = ROOT / "locale"

#: the suffixes RULES.md names, plus `_recurring`, which named a second
#: file for an intent that already had one
DUPLICATE_SUFFIX = re.compile(r"_(alt|2|extra|alias|recurring)$")


#: one recurring line per locale, quoted from the deleted
#: create_reminder_recurring.intent files
RECURRING_LINE_PER_LOCALE = {
    "ca-ES": "recorda'm que passegi el gos els matins entre setmana a les 7",
    "cs-CZ": "připomeň mi venčit psa každé všední ráno v 7",
    "da-DK": "mind mig hver hverdags aften om at ringe til mor klokken 6",
    "de-DE": "erinnere mich jeden Wochentag morgens um 8 an meine Medizin",
    "en-US": "remind me to stretch weekend mornings at 8",
    "es-ES": "recuérdame ir al trabajo entre semana por la mañana a las 8",
    "eu-ES": "gogorarazi lanera joateko astegunetan goizeko 8etan",
    "fr-FR": "rappelle-moi chaque soir de semaine d'appeler ma mère à 6 heures",
    "gl-ES": "lémbrame pasear o can entre semana pola mañá ás 7",
    "hu-HU": "emlékeztess minden hétköznap reggel 8-kor a gyógyszeremre",
    "it-IT": "ricordami ogni sera feriale di chiamare mia madre alle 6",
    "kab": "smektay-iyi ad ssiweḍ aqjun yal ṣṣbeḥ n ussan n ddurt ɣef 7",
    "nl-NL": "herinner me elke doordeweekse ochtend om 8 uur aan mijn medicijnen",
    "pl-PL": "przypominaj mi każdego ranka w tygodniu o lekach o 8",
    "pt-BR": "me lembre de pagar o aluguel toda terça às 10 30",
    "pt-PT": "lembra-me todas as noites úteis de ligar à minha mãe às 6",
    "ru-RU": "напоминай мне каждый вечер в будни звонить маме в 6",
    "sv-FI": "muistuta minua menemään töihin joka arkiaamu kello 8",
    "sv-SE": "påminn mig varje vardagskväll om att ringa mamma klockan 6",
}


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

    def test_every_locale_keeps_its_recurring_lines(self):
        """The fold moved the lines, it did not drop them.

        The two checks above pass on a tree where the recurring file was
        deleted and its lines thrown away. This one reads one line per
        locale out of the surviving file, so a fold that lost the phrasings
        fails here. Each line is the shortest recurring line that locale
        shipped, quoted from the deleted file.
        """
        # locale -> one line the deleted create_reminder_recurring.intent
        # carried, which create_reminder.intent must now hold verbatim
        expected = RECURRING_LINE_PER_LOCALE
        for locale, line in sorted(expected.items()):
            path = LOCALE / locale / "intent" / "create_reminder.intent"
            lines = [l.strip() for l in
                     path.read_text(encoding="utf-8").splitlines()]
            self.assertIn(line, lines, (
                f"{locale}: create_reminder.intent lost the recurring "
                f"phrasing {line!r}"
            ))

    def test_no_forwarding_recurring_handler_remains(self):
        source = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("def handle_create_reminder_recurring", source)
        self.assertNotIn(
            '@intent_handler("create_reminder_recurring.intent")', source)


if __name__ == "__main__":
    unittest.main()
