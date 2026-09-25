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
"""
import json
from pathlib import Path

import pytest

END2END = Path(__file__).resolve().parent
LOCALE = END2END.parents[1] / "locale" / "en-US" / "intent"
GOLDEN = END2END / "golden_utterances_en-US.jsonl"


def _rows(path=GOLDEN):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _every_row():
    """Every row of every locale, not just en-US.

    The en-US file was the only one read here, so a label naming nothing in
    any other locale had nothing to catch it: the suite that drives the rows
    through a pipeline is the only other reader, and it was dark. 445 rows in
    17 files were unchecked; 184 of them are en-US.
    """
    for path in sorted(END2END.glob("golden_utterances_*.jsonl")):
        lang = path.name[len("golden_utterances_"):-len(".jsonl")]
        for row in _rows(path):
            yield lang, row


def _registered():
    return {p.stem for p in LOCALE.glob("*.intent")}


@pytest.mark.parametrize("row", list(_rows()), ids=lambda r: r["utterance"])
def test_the_label_names_a_registered_intent(row):
    label = row["intent_label"]
    assert label in _registered(), (
        f"{row['utterance']!r}: {label!r} is not an intent this skill "
        f"registers in locale/en-US")


def test_the_locale_directory_is_not_empty():
    """The control: an empty glob would make every case above vacuous."""
    assert len(_registered()) > 10


def test_the_family_name_is_not_an_intent():
    """The control in the other direction, on the check itself."""
    assert "ChangeProperties" not in _registered()


@pytest.mark.parametrize(
    "lang,row", list(_every_row()),
    ids=lambda v: v if isinstance(v, str) else v["utterance"])
def test_every_locale_label_names_a_registered_intent(lang, row):
    """A golden row in any locale names an intent the skill registers.

    The label is checked against en-US, the reference locale: a locale that
    does not ship a given .intent file still answers to that intent, so the
    registered set is en-US's, not that locale's own.
    """
    label = row["intent_label"]
    assert label in _registered(), (
        f"{lang} {row['utterance']!r}: {label!r} is not an intent this skill "
        f"registers in locale/en-US")


def test_every_locale_file_is_read():
    """The control: this suite is worthless if the glob finds one file."""
    langs = {lang for lang, _ in _every_row()}
    assert len(langs) > 10, f"only {len(langs)} locale file(s) read"
    assert "en-US" in langs


def test_only_kab_has_no_golden_file():
    """Every locale the skill ships has golden rows, except kab.

    kab is the one gap and it is pinned here so it cannot quietly grow: a
    second locale losing its golden file fails this, and kab gaining one
    fails it too, which is the day to delete this test.
    """
    shipped = {p.name for p in (END2END.parents[1] / "locale").iterdir()
               if p.is_dir()}
    covered = {lang for lang, _ in _every_row()}
    assert shipped - covered == {"kab"}, (
        f"locales with no golden file: {sorted(shipped - covered)}")
