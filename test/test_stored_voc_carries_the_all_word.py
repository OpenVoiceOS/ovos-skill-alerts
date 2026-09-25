"""The all-word a locale's own intent file uses must be in its stored.voc.

`delete_list_entries.intent` offers two branches. One says "delete
everything": the handler takes it as "all of them" and deletes without asking.
The other names items and goes to the interactive follow-up. The handler tells
them apart with `voc_match(utterance, "stored", lang)`
(`__init__.py:1033` and `:1093`), so a locale whose intent line uses an
all-word that `stored.voc` does not carry sends that line to the wrong branch:
the word is taken as an item name, and with todos stored the skill answers
`list_todo_dont_exist` and deletes nothing.

#240 found this in en-US and fixed four locales (en-US `everything`, da-DK
`alt`, nl-NL `alles`, sv-SE `allt`). Its reviewer found five more still broken,
each with a near-miss already in the voc: it-IT had `tutti` and not `tutto`,
fr-FR `tous` and not `tout`, pt-PT `todo`/`todos` and not `tudo`, cs-CZ
`všechny` and not `všechno`, hu-HU `minden`/`egész`/`teljes` and not `összes`.
A near miss is what makes this class of defect quiet: the voc looks populated.

This test asks the question at the level the defect lives on, so it does not
need to know any language. For each locale that ships the intent file, at least
one expansion of that locale's OWN lines must satisfy the handler's own
`voc_match`. Nothing here is a translated sentence: every string tested is read
out of the repository.
"""
import os
import re
from pathlib import Path

import pytest

from util.locale import voc_match

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locale"
INTENT = "intent/delete_list_entries.intent"

# The locales whose delete-everything line carries an all-word: the four #240
# fixed and the five its review found. A locale not listed here is not
# asserted, because whether its phrasing has an all-word at all is a question
# for its own speaker, not for this test.
CARRY_AN_ALL_WORD = [
    "en-US", "da-DK", "nl-NL", "sv-SE",
    "it-IT", "fr-FR", "pt-PT", "cs-CZ", "hu-HU",
]


def expansions(path: Path):
    """Every literal sentence the template lines resolve to.

    (a|b) picks one alternative and [x] is (x|), the same reading the matcher
    uses. Slots are dropped: `voc_match` looks for a vocabulary word, and a
    slot value is never one.
    """
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for s in _expand(line):
            s = re.sub(r"\{[^}]*\}", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            if s:
                out.append(s)
    return out


def _expand(line):
    m = re.search(r"\(([^()\[\]]*)\)|\[([^()\[\]]*)\]", line)
    if not m:
        return [line]
    whole = m.group(0)
    if m.group(1) is not None:
        choices = m.group(1).split("|")
    else:
        choices = m.group(2).split("|") + [""]
    out = []
    for c in choices:
        out.extend(_expand(line.replace(whole, c, 1)))
    return out


@pytest.mark.parametrize("lang", CARRY_AN_ALL_WORD)
def test_the_locales_all_word_reaches_the_handler(lang):
    path = LOCALES / lang / INTENT
    assert path.is_file(), f"{lang} ships no {INTENT}"
    lines = expansions(path)
    assert lines, f"{lang}: {INTENT} expanded to nothing"
    matched = [s for s in lines if voc_match(s, "stored", lang=lang)]
    assert matched, (
        f"{lang}: no expansion of its own {INTENT} satisfies "
        f"voc_match(..., 'stored'), so its delete-everything line goes to the "
        f"interactive branch, the all-word is taken as an item name, and with "
        f"todos stored the skill answers list_todo_dont_exist and deletes "
        f"nothing. Add that locale's all-word to locale/{lang}/vocab/"
        f"stored.voc. Lines read: {lines!r}"
    )


def test_a_line_with_no_all_word_does_not_match():
    """The negative control for the test above.

    Without it, a `voc_match` that answered True for every string would make
    the whole suite green. "clear my todo list" is an en-US phrasing #240
    recorded as belonging to the interactive branch by design.
    """
    assert not voc_match("clear my todo list", "stored", lang="en-US")


def test_the_check_can_fail():
    """The second control: the assertion is reachable.

    A locale code that ships no vocabulary must not match, so a `voc_match`
    that swallowed a missing resource and returned True would be caught here
    rather than reading as nine passes.
    """
    assert not voc_match("delete everything from my list", "stored",
                         lang="zz-ZZ")
