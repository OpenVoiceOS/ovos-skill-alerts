"""Guard against a vocabulary entry that matches every utterance.

`OVOSSkill.voc_match` normalises both the utterance and each vocabulary
entry with `remove_accents_and_punct`, which strips every punctuation
character, and then tests `re.match(r'.*\b' + re.escape(entry) + r'\b.*')`.

An entry made only of punctuation normalises to the empty string, and
`.*\b\b.*` matches any utterance that contains a word boundary. One such
line therefore makes its whole `.voc` answer True for everything the user
says, in that locale only.

locale/eu-ES shipped three of them, `...` in repeat.voc and stored.voc and
`***` in noise_words.voc, so in Basque every request looked recurring and
stored. The blank first line of several files is harmless: the resource
loader drops empty lines before this point, and only a non-empty line that
normalises to empty survives to reach voc_match.
"""
import string
import unicodedata
from pathlib import Path

import pytest

LOCALE = Path(__file__).parent.parent / "locale"

_RM = [c for c in string.punctuation if c not in ("{", "}")]


def _normalise(text: str) -> str:
    """The same transform `ovos_utils.text_utils.remove_accents_and_punct` applies."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed
                   if unicodedata.category(c) != "Mn" and c not in _RM)


def _voc_files():
    return sorted(LOCALE.glob("*/vocab/*.voc")) + sorted(LOCALE.glob("*/*.voc"))


def test_there_are_voc_files_to_check():
    assert _voc_files(), "no .voc files found; the glob below would pass vacuously"


@pytest.mark.parametrize("voc", _voc_files(), ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_no_entry_normalises_to_empty(voc):
    offenders = [
        (n, line) for n, line in enumerate(voc.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip() and not _normalise(line).strip()
    ]
    assert not offenders, (
        f"{voc.parent.parent.name}/{voc.name} has entries made only of punctuation, "
        f"which make voc_match answer True for every utterance in this locale: {offenders}"
    )
