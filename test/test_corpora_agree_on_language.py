"""Every test utterance is tagged with the language it is written in.

`list_kind_probes.jsonl` and the `golden_utterances_<lang>.jsonl` files tag
each utterance with a locale. A tag that names the wrong language makes the
tests that read it check Finnish sentences against Swedish vocabulary, and the
failures they produce point everywhere except at the tag. Renaming a locale
tree without re-tagging its rows does exactly that.

The rule is about the language subtag, not the whole locale code. One utterance
may appear under `sv-SE` and `sv-FI`, because both are Swedish; it may appear
under `es-ES` and `gl-ES` when it is valid in both. It may not appear under a
locale whose own resource files share no word with it.

A locale's words are every word of three letters or more in its `.voc`,
`.entity`, `.list`, `.word`, `.dialog` and `.intent` files, with `{slot}` names
removed. The heuristic is built to miss rather than to accuse: it cannot tell
two close languages apart (Spanish rows tagged Galician mostly pass), but a
corpus tagged with an unrelated language fails on many of its rows, and one
row is enough to fail the test.
"""
import json
import os
import re
import unittest
from collections import defaultdict

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TEST_DIR)
LOCALE_ROOT = os.path.join(REPO_ROOT, "locale")


def _corpora():
    """(path, rows) for every corpus that tags an utterance with a language."""
    found = []
    probes = os.path.join(TEST_DIR, "list_kind_probes.jsonl")
    if os.path.isfile(probes):
        found.append(probes)
    end2end = os.path.join(TEST_DIR, "end2end")
    if os.path.isdir(end2end):
        found.extend(os.path.join(end2end, name)
                     for name in sorted(os.listdir(end2end))
                     if name.startswith("golden_utterances_")
                     and name.endswith(".jsonl"))
    for path in found:
        with open(path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        yield os.path.relpath(path, REPO_ROOT), rows


SLOT = re.compile(r"\{[^}]*\}")
WORD_FILES = (".voc", ".entity", ".list", ".word", ".dialog", ".intent")


def _subtag(lang):
    return lang.split("-")[0].lower()


def _tokens(text):
    return {word for word in re.findall(r"[^\W\d_]+", text.lower())
            if len(word) > 2}


def _locale_words(lang):
    """Every word of three letters or more in a locale's resource files."""
    words = set()
    for root, _dirs, files in os.walk(os.path.join(LOCALE_ROOT, lang)):
        for name in files:
            if not name.endswith(WORD_FILES):
                continue
            with open(os.path.join(root, name), encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        line = SLOT.sub(" ", line)
                        words |= _tokens(line)
    return words


class TestCorporaAgreeOnLanguage(unittest.TestCase):
    def test_no_utterance_is_tagged_with_two_languages(self):
        """The same sentence under two language subtags is allowed only when
        each of those locales shares a word with it. Close languages share
        short sentences; a re-tag left half done does not."""
        vocab = {}
        langs = defaultdict(set)
        where = defaultdict(set)
        for path, rows in _corpora():
            for row in rows:
                utterance = row.get("utterance")
                lang = row.get("lang")
                if not utterance or not lang:
                    continue
                langs[utterance].add(lang)
                where[utterance].add(f"{path}:{lang}")
        disagreements = []
        for utterance, tags in sorted(langs.items()):
            if len({_subtag(tag) for tag in tags}) < 2:
                continue
            tokens = _tokens(utterance)
            unsupported = []
            for tag in sorted(tags):
                if tag not in vocab:
                    vocab[tag] = _locale_words(tag)
                if not tokens & vocab[tag]:
                    unsupported.append(tag)
            if unsupported:
                disagreements.append(
                    f"{utterance!r} is tagged "
                    + ", ".join(sorted(where[utterance]))
                    + f"; locale/{', locale/'.join(unsupported)} "
                    "shares no word with it")
        self.assertEqual(
            disagreements, [],
            f"{len(disagreements)} utterances carry two language subtags "
            "across the test corpora:\n  " + "\n  ".join(disagreements))

    def test_every_corpus_language_is_a_shipped_locale(self):
        shipped = {name for name in os.listdir(LOCALE_ROOT)
                   if os.path.isdir(os.path.join(LOCALE_ROOT, name))}
        unknown = set()
        for path, rows in _corpora():
            for row in rows:
                lang = row.get("lang")
                if lang and lang not in shipped:
                    unknown.add(f"{path} tags {lang}, which locale/ does not hold")
        self.assertEqual(sorted(unknown), [])

    def test_a_golden_corpus_tags_the_locale_in_its_own_name(self):
        wrong = []
        for path, rows in _corpora():
            name = os.path.basename(path)
            if not name.startswith("golden_utterances_"):
                continue
            expected = name[len("golden_utterances_"):-len(".jsonl")]
            for row in rows:
                if row.get("lang") and row["lang"] != expected:
                    wrong.append(f"{path} holds a row tagged {row['lang']}")
        self.assertEqual(sorted(set(wrong)), [])

    def test_no_row_is_tagged_a_locale_whose_words_it_never_uses(self):
        """The tag has to be supported by the locale's own vocabulary.

        It fires only when the tagged locale shares no word with the row and
        a locale of another language shares at least two, so a shared proper
        noun or a chance collision cannot trip it. A locale of the same
        language (`sv-SE` for an `sv-FI` row) is never the other locale.
        """
        shipped = sorted(name for name in os.listdir(LOCALE_ROOT)
                         if os.path.isdir(os.path.join(LOCALE_ROOT, name)))
        vocab = {lang: _locale_words(lang) for lang in shipped}
        unsupported = []
        for path, rows in _corpora():
            for row in rows:
                lang, utterance = row.get("lang"), row.get("utterance")
                if not lang or not utterance or lang not in vocab:
                    continue
                tokens = _tokens(utterance)
                if not tokens or tokens & vocab[lang]:
                    continue
                best = max(((len(tokens & vocab[other]), other)
                            for other in shipped
                            if _subtag(other) != _subtag(lang)),
                           default=(0, None))
                if best[0] >= 2:
                    unsupported.append(
                        f"{path}: the {lang} row {utterance!r} shares no word "
                        f"with locale/{lang} and {best[0]} with "
                        f"locale/{best[1]}")
        self.assertEqual(
            unsupported, [],
            f"{len(unsupported)} rows carry a locale tag their own locale does "
            "not support:\n  " + "\n  ".join(unsupported))


if __name__ == "__main__":
    unittest.main()
