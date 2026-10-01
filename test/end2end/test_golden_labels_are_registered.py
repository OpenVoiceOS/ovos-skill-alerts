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


def _rows():
    with GOLDEN.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


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
