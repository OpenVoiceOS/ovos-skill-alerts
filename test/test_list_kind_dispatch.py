"""Guard the todo/list dispatch inside the merged list intents.

QueryListEntries and DeleteListEntries each accept two kinds of request: one
about the todo list as a whole, one about the entries of a named list. Which
one the user meant is decided by ``voc_match(utterance, "todo")``, so every
phrasing the merged templates accept has to land on the right side of that
check. Before the merge the two kinds lived in separate intent files and the
split was implicit in which file a line came from; list_kind_probes.jsonl
carries that split forward, one probe per pre-merge template line.

Matching mirrors ``util/locale.py``'s ``voc_match``: case-insensitive, on word
boundaries, against the expanded entries of the .voc file.
"""
import json
import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ovos_bus_client.message import Message
from ovos_spec_tools.expansion import expand

from ovos_skill_alerts import AlertSkill

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_ROOT = os.path.join(REPO_ROOT, "locale")
PROBES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "list_kind_probes.jsonl")


def _vocab(lang):
    path = os.path.join(LOCALE_ROOT, lang, "vocab", "todo.voc")
    words = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                words.extend(expand(line))
    return [w.strip().lower() for w in words if w.strip()]


def _is_todo_kind(utterance, words):
    utterance = utterance.lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", utterance) for w in words)


def _probes():
    with open(PROBES, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestListKindDispatch(unittest.TestCase):
    def test_every_probe_dispatches_to_its_kind(self):
        failures = []
        for probe in _probes():
            words = _vocab(probe["lang"])
            got = "todo" if _is_todo_kind(probe["utterance"], words) else "list"
            if got != probe["kind"]:
                failures.append(
                    f"{probe['lang']}/{probe['intent']}: "
                    f"{probe['utterance']!r} dispatches as {got}, "
                    f"expected {probe['kind']} "
                    f"(from {probe['source_template']!r})")
        self.assertEqual(
            failures, [],
            f"{len(failures)} of {len(_probes())} probes dispatch to the "
            "wrong kind:\n" + "\n".join(failures))

    def test_probes_cover_every_locale_and_both_kinds(self):
        probes = _probes()
        langs = {p["lang"] for p in probes}
        expected = {d for d in os.listdir(LOCALE_ROOT)
                    if os.path.isfile(os.path.join(
                        LOCALE_ROOT, d, "intent", "QueryListEntries.intent"))}
        self.assertEqual(langs, expected)
        for lang in sorted(langs):
            kinds = {p["kind"] for p in probes if p["lang"] == lang}
            self.assertEqual(kinds, {"todo", "list"}, f"{lang} probes")


class TestHandlerDispatch(unittest.TestCase):
    """The dispatchers route to a kind without needing a live skill."""

    def _skill(self):
        return SimpleNamespace(lang="en-us",
                               _speak_todo_reminder_names=Mock(),
                               handle_todo_list_entries=Mock(),
                               _delete_todo_entries=Mock(),
                               _delete_list_entries=Mock())

    def test_query_routes_todo_and_list_phrasings_apart(self):
        for utterance, taken, skipped in (
                ("what's on my todo list",
                 "_speak_todo_reminder_names", "handle_todo_list_entries"),
                ("what items are on my shopping list",
                 "handle_todo_list_entries", "_speak_todo_reminder_names")):
            with self.subTest(utterance):
                skill = self._skill()
                AlertSkill.handle_query_list_entries(
                    skill, Message("test", {"utterance": utterance}))
                getattr(skill, taken).assert_called_once()
                getattr(skill, skipped).assert_not_called()

    def test_delete_routes_todo_and_list_phrasings_apart(self):
        for utterance, taken, skipped in (
                ("delete my todo list",
                 "_delete_todo_entries", "_delete_list_entries"),
                ("delete the items from my shopping list",
                 "_delete_list_entries", "_delete_todo_entries")):
            with self.subTest(utterance):
                skill = self._skill()
                AlertSkill.handle_delete_list_entries(
                    skill, Message("test", {"utterance": utterance}))
                getattr(skill, taken).assert_called_once()
                getattr(skill, skipped).assert_not_called()


if __name__ == "__main__":
    unittest.main()
