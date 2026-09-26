"""Every golden corpus file this directory ships must be dispatched by a runner.

A file nobody reads is not coverage, and nothing in a green run says it is
missing. This repository was in exactly that state: 18
``golden_utterances_<lang>.jsonl`` files and none of them dispatched, because
the multilang runner carried a blanket ``pytest.mark.skip`` for
OpenVoiceOS/ovoscope#179 while two of the files -- en-US and pt-BR -- were not
even in the list the runner reads (skills-qa census, T-5487).

These checks need no MiniCroft: they read the runner's own module-level lists,
so they are fast and they fail for one reason each.
"""
from pathlib import Path

import pytest

from .test_golden_utterances_multilang import (
    ALL_ROWS, LANGS, ROW_LANGS,
)

END2END = Path(__file__).resolve().parent


def _shipped_langs():
    return {p.name[len("golden_utterances_"):-len(".jsonl")]
            for p in END2END.glob("golden_utterances_*.jsonl")}


def test_the_corpus_is_found():
    """The control: an empty glob would make every check below vacuous."""
    shipped = _shipped_langs()
    assert len(shipped) > 10, f"{len(shipped)} corpus files found; the glob is stale"


def test_every_shipped_corpus_file_is_read_by_the_runner():
    missing = sorted(_shipped_langs() - set(ROW_LANGS))
    assert not missing, (
        "these locales ship a golden corpus that the runner never reads, so "
        f"their rows are never dispatched: {', '.join(missing)}. Add them to "
        "ROW_LANGS, or delete the file and say why in the module docstring")


def test_every_locale_the_runner_reads_ships_a_corpus():
    missing = sorted(l for l in ROW_LANGS
                     if not (END2END / f"golden_utterances_{l}.jsonl").is_file())
    assert not missing, (
        f"ROW_LANGS names locales with no corpus file: {', '.join(missing)}")


def test_the_runner_collected_rows_for_every_locale_it_reads():
    """A file that exists and holds only skipped rows dispatches nothing."""
    by_lang = {}
    for row in ALL_ROWS:
        by_lang.setdefault(row["lang"], 0)
        by_lang[row["lang"]] += 1
    empty = sorted(l for l in ROW_LANGS if not by_lang.get(l))
    assert not empty, (
        "these locales are read but contribute no dispatched row (every row "
        f"filtered, e.g. needs_manual): {', '.join(empty)}")


def test_en_us_is_the_primary_language_and_not_a_secondary_one():
    """Pins the reason en-US is in ROW_LANGS and not in LANGS.

    The MiniCroft boots with en-US as its primary language; LANGS is passed as
    ``secondary_langs``. Listing en-US in both would ask the harness for the
    primary language a second time.
    """
    assert "en-US" not in LANGS
    assert ROW_LANGS[0] == "en-US"


@pytest.mark.parametrize("lang", sorted(_shipped_langs()))
def test_the_corpus_file_is_not_empty(lang):
    path = END2END / f"golden_utterances_{lang}.jsonl"
    assert [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()], \
        f"{path.name} ships no row"
