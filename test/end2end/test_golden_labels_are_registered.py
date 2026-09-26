"""Every golden row must name an intent this skill registers.

This check is deliberately static: it reads the labels against the
``.intent`` files on disk and boots nothing. The suite that drives these rows
through a real pipeline is skipped while ovoscope#179 is open, so a label
that names nothing has no other way of being caught -- and one did.

21 rows named ``ChangeProperties``. No locale ships a
``ChangeProperties.intent`` and no handler registers that name: it is the
name of a FAMILY of four intents, used as such in ``test_intents.yaml`` and
in ``_gate_probe.py``. As a golden label it trained a class no skill answers
to.

The check reads every locale, not only en-US. It read en-US alone when
``create_reminder_recurring`` was folded into ``create_reminder``: the file
went in all 19 locales, and the five pt-BR rows that still named the old
label passed this guard because no en-US row carried it. A label is checked
against the ``.intent`` files of its own locale.
"""
import json
from pathlib import Path

import pytest

END2END = Path(__file__).resolve().parent
LOCALE_ROOT = END2END.parents[1] / "locale"


def _rows():
    for path in sorted(END2END.glob("golden_utterances_*.jsonl")):
        lang = path.name[len("golden_utterances_"):-len(".jsonl")]
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    row.setdefault("lang", lang)
                    yield row


def _registered(lang="en-US"):
    return {p.stem for p in (LOCALE_ROOT / lang / "intent").glob("*.intent")}


@pytest.mark.parametrize("row", list(_rows()),
                         ids=lambda r: f"{r['lang']}-{r['utterance']}")
def test_the_label_names_a_registered_intent(row):
    label, lang = row["intent_label"], row["lang"]
    assert label in _registered(lang), (
        f"{row['utterance']!r}: {label!r} is not an intent this skill "
        f"registers in locale/{lang}")


def test_every_golden_file_has_a_locale_directory():
    """The control: a row whose locale has no intent directory is vacuous."""
    langs = sorted({r["lang"] for r in _rows()})
    assert len(langs) > 10, f"{langs}: the golden glob is stale"
    missing = [lang for lang in langs if not _registered(lang)]
    assert missing == [], f"{missing}: no intent file read for this locale"


def test_the_locale_directory_is_not_empty():
    """The control: an empty glob would make every case above vacuous."""
    assert len(_registered()) > 10


def test_the_family_name_is_not_an_intent():
    """The control in the other direction, on the check itself."""
    assert "ChangeProperties" not in _registered()
