"""Keep each locale's todo.voc in sync with its own todo-kind intent templates.

The todo/list distinction is carried by the wording of the intent templates,
but code that needs to tell the two apart can only ask ``voc_match(utterance,
"todo")``. That only works if every phrasing the todo-kind templates accept
contains a word from todo.voc, and no phrasing the list-kind templates accept
does. The two resource families are authored independently per locale, so
nothing but this test keeps them agreeing.

Matching mirrors ``util/locale.py``'s ``voc_match``: case-insensitive, on word
boundaries, against the expanded entries of the .voc file.
"""
import os
import re
import unittest

from ovos_spec_tools.expansion import expand

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_ROOT = os.path.join(REPO_ROOT, "locale")

TODO_KIND = ("QueryTodoEntries", "DeleteTodoEntries")
LIST_KIND = ("QueryListEntries", "DeleteListEntries")

SLOT = re.compile(r"\{\w+\}")


def _lines(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                yield line


def _expansions(locale, intent_name):
    path = os.path.join(LOCALE_ROOT, locale, "intent", f"{intent_name}.intent")
    if not os.path.isfile(path):
        return
    for line in _lines(path):
        for utterance in expand(line):
            utterance = SLOT.sub(" ", utterance)
            utterance = re.sub(r"\s+", " ", utterance).strip()
            if utterance:
                yield line, utterance


def _vocab(locale):
    path = os.path.join(LOCALE_ROOT, locale, "vocab", "todo.voc")
    if not os.path.isfile(path):
        return []
    words = []
    for line in _lines(path):
        words.extend(expand(line))
    return [w.strip().lower() for w in words if w.strip()]


def _matches(utterance, words):
    utterance = utterance.lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", utterance) for w in words)


def _locales():
    return sorted(d for d in os.listdir(LOCALE_ROOT)
                  if os.path.isdir(os.path.join(LOCALE_ROOT, d, "intent")))


class TestTodoVocabReconciliation(unittest.TestCase):
    def test_todo_templates_are_covered_by_todo_vocab(self):
        failures = []
        for locale in _locales():
            words = _vocab(locale)
            for intent_name in TODO_KIND:
                for line, utterance in _expansions(locale, intent_name):
                    if not _matches(utterance, words):
                        failures.append(
                            f"{locale}/{intent_name}: {utterance!r} "
                            f"(from {line!r}) matches no todo.voc entry")
        self.assertEqual(
            failures, [],
            f"{len(failures)} todo-kind phrasings would be mistaken for "
            "list-kind ones:\n" + "\n".join(failures))

    def test_list_templates_are_not_covered_by_todo_vocab(self):
        failures = []
        for locale in _locales():
            words = _vocab(locale)
            for intent_name in LIST_KIND:
                for line, utterance in _expansions(locale, intent_name):
                    if _matches(utterance, words):
                        hit = [w for w in words if _matches(utterance, [w])]
                        failures.append(
                            f"{locale}/{intent_name}: {utterance!r} "
                            f"(from {line!r}) matches todo.voc {hit}")
        self.assertEqual(
            failures, [],
            f"{len(failures)} list-kind phrasings would be mistaken for "
            "todo-kind ones:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
