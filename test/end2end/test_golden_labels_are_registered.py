"""Every golden row must name an intent this skill registers in its locale.

This check is deliberately static: it reads the labels of every
``golden_utterances_<lang>.jsonl`` against the ``.intent`` files on disk in
``locale/<lang>/intent`` and boots nothing. The m2v golden runner skips some
intents in its per-intent floor (``GOLDEN_INTENT_GAPS``), so a deleted
``.intent`` file for such an intent fails here and nowhere else.

A family name is not an intent: ``ChangeProperties`` names four intents in
``test_intents.yaml`` and ``_gate_probe.py``, but no locale ships a
``ChangeProperties.intent`` and no handler registers that name.
"""
import json
from pathlib import Path

import pytest

END2END = Path(__file__).resolve().parent
LOCALE_ROOT = END2END.parents[1] / "locale"
GOLDEN_FILES = sorted(END2END.glob("golden_utterances_*.jsonl"))


def _lang(path):
    return path.stem.removeprefix("golden_utterances_")


def _rows():
    for path in GOLDEN_FILES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield _lang(path), json.loads(line)


def _registered(lang):
    return {p.stem for p in (LOCALE_ROOT / lang / "intent").glob("*.intent")}


@pytest.mark.parametrize("lang,row", list(_rows()),
                         ids=lambda value: value if isinstance(value, str) else value["utterance"])
def test_the_label_names_a_registered_intent(lang, row):
    label = row["intent_label"]
    assert label in _registered(lang), (
        f"{row['utterance']!r}: {label!r} is not an intent this skill "
        f"registers in locale/{lang}")


def test_every_golden_file_is_checked():
    """The control: an empty glob would make every case above vacuous."""
    assert len(GOLDEN_FILES) >= 20
    assert all(len(_registered(_lang(path))) > 10 for path in GOLDEN_FILES)


def test_the_family_name_is_not_an_intent():
    """The control in the other direction, on the check itself."""
    assert all("ChangeProperties" not in _registered(_lang(path)) for path in GOLDEN_FILES)
