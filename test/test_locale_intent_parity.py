"""Every shipped locale has every en-US intent file, with at least one sample.

The skill registers its intents from ``locale/<lang>/intent/<name>.intent``.
A locale that lacks a file, or ships one with no sample line, leaves that
intent unreachable in that language. This test reads the files on disk and
boots nothing.
"""
from pathlib import Path

import pytest

LOCALE_ROOT = Path(__file__).resolve().parents[1] / "locale"
REFERENCE = "en-US"
REFERENCE_INTENTS = sorted(p.name for p in (LOCALE_ROOT / REFERENCE / "intent").glob("*.intent"))
SHIPPED = sorted(d.name for d in LOCALE_ROOT.iterdir()
                 if d.is_dir() and d.name != REFERENCE and any(d.rglob("*.intent")))


def _samples(path):
    return [line for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


@pytest.mark.parametrize("lang", SHIPPED)
@pytest.mark.parametrize("intent", REFERENCE_INTENTS)
def test_locale_ships_the_intent_with_a_sample(lang, intent):
    path = LOCALE_ROOT / lang / "intent" / intent
    assert path.is_file(), f"locale/{lang}/intent/{intent} is missing"
    assert _samples(path), f"locale/{lang}/intent/{intent} has no sample line"


def test_the_reference_and_locales_are_found():
    """The control: an empty glob would make every case above vacuous."""
    assert len(REFERENCE_INTENTS) > 10
    assert len(SHIPPED) >= 20
