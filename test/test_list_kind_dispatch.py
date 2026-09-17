"""Guard the todo/list dispatch inside the merged list intents.

query_list_entries and delete_list_entries each accept two kinds of request: one
about the todo list as a whole, one about the entries of a named list. The
templates put the list the user named in the ``{list_name}`` slot, and the
todo list is one of those names. A ``list_name`` that todo.voc does not hold
asks for a named list. A ``list_name`` that todo.voc holds asks for the todo
list, unless a stored list has that name. With no ``list_name``,
``voc_match(utterance, "todo")`` decides. Every phrasing the merged templates
accept has to land on the right side of that rule. Before the merge the two
kinds lived in separate intent files; list_kind_probes.jsonl carries that
split forward: one probe per pre-merge template line, plus one probe per locale
and intent whose list name is a word from that locale's todo.voc. The
``list_name`` of each probe is the slot value the author expects; the file
records intent, not a measured engine run. The end-to-end suite measures the
slot on the real pipeline.

The keyword part mirrors ``util/locale.py``'s ``voc_match``: case-insensitive,
on word boundaries, against the expanded entries of the .voc file.
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


def _has_todo_word(text, words):
    text = text.lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def _is_todo_kind(probe, words, stored_lists=()):
    """Mirror AlertSkill._is_todo_kind with a set of stored list names."""
    list_name = probe.get("list_name")
    if list_name:
        return _has_todo_word(list_name, words) and list_name not in stored_lists
    return _has_todo_word(probe["utterance"], words)


def _probes():
    with open(PROBES, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestListKindDispatch(unittest.TestCase):
    def test_every_probe_dispatches_to_its_kind(self):
        failures = []
        for probe in _probes():
            words = _vocab(probe["lang"])
            # a list-kind probe names a list that the user has stored
            stored = {probe["list_name"]} if probe.get("list_name") else set()
            got = "todo" if _is_todo_kind(probe, words, stored) else "list"
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

    def test_every_locale_probes_a_list_named_after_a_todo_word(self):
        """A list name that holds a todo word must stay a list request."""
        by_lang = {}
        for probe in _probes():
            if probe["kind"] != "list" or not probe.get("list_name"):
                continue
            words = _vocab(probe["lang"])
            if _has_todo_word(probe["list_name"], words):
                by_lang.setdefault(probe["lang"], set()).add(probe["intent"])
                self.assertTrue(
                    _is_todo_kind(probe, words),
                    f"{probe['lang']}: todo word {probe['list_name']!r} in the "
                    "list_name slot with no stored list must read the todo list")
        expected = {d for d in os.listdir(LOCALE_ROOT)
                    if os.path.isfile(os.path.join(
                        LOCALE_ROOT, d, "intent", "query_list_entries.intent"))}
        missing = sorted(expected - set(by_lang))
        self.assertEqual(missing, [],
                         "locales with no todo-word list name probe")
        for lang in sorted(by_lang):
            self.assertEqual(by_lang[lang],
                             {"query_list_entries", "delete_list_entries"},
                             f"{lang} todo-word name probes")

    def test_probes_cover_every_locale_and_both_kinds(self):
        probes = _probes()
        langs = {p["lang"] for p in probes}
        expected = {d for d in os.listdir(LOCALE_ROOT)
                    if os.path.isfile(os.path.join(
                        LOCALE_ROOT, d, "intent", "query_list_entries.intent"))}
        self.assertEqual(langs, expected)
        for lang in sorted(langs):
            kinds = {p["kind"] for p in probes if p["lang"] == lang}
            self.assertEqual(kinds, {"todo", "list"}, f"{lang} probes")


class TestHandlerDispatch(unittest.TestCase):
    """The dispatchers route to a kind without needing a live skill."""

    def _skill(self, stored_lists=()):
        lists = [SimpleNamespace(alert_name=n, children=["item"])
                 for n in stored_lists]
        skill = SimpleNamespace(lang="en-us",
                                _get_alerts_list=lambda alert_type, name="": [
                                    a for a in lists if a.alert_name == name],
                                _speak_todo_reminder_names=Mock(),
                                handle_todo_list_entries=Mock(),
                                _delete_todo_entries=Mock(),
                                _delete_list_entries=Mock())
        skill._is_todo_kind = lambda message: AlertSkill._is_todo_kind(
            skill, message)
        return skill

    def test_query_routes_todo_and_list_phrasings_apart(self):
        for utterance, name, stored, taken, skipped in (
                ("what's on my todo", None, (),
                 "_speak_todo_reminder_names", "handle_todo_list_entries"),
                ("what is on my todo list", "todo", (),
                 "_speak_todo_reminder_names", "handle_todo_list_entries"),
                ("what is on the notes list", "notes", ("notes",),
                 "handle_todo_list_entries", "_speak_todo_reminder_names"),
                ("what items are on my shopping list", "shopping", (),
                 "handle_todo_list_entries", "_speak_todo_reminder_names"),
                ("what items are on my notes list", "notes", (),
                 "_speak_todo_reminder_names", "handle_todo_list_entries")):
            with self.subTest(utterance):
                skill = self._skill(stored)
                data = {"utterance": utterance}
                if name:
                    data["list_name"] = name
                AlertSkill.handle_query_list_entries(
                    skill, Message("test", data))
                getattr(skill, taken).assert_called_once()
                getattr(skill, skipped).assert_not_called()

    def test_delete_routes_todo_and_list_phrasings_apart(self):
        for utterance, name, stored, taken, skipped in (
                ("delete my todo list", None, (),
                 "_delete_todo_entries", "_delete_list_entries"),
                ("delete everything from my todo list", "todo", (),
                 "_delete_todo_entries", "_delete_list_entries"),
                ("delete the items from my shopping list", "shopping", (),
                 "_delete_list_entries", "_delete_todo_entries"),
                ("delete everything from my memo list", "memo", ("memo",),
                 "_delete_list_entries", "_delete_todo_entries")):
            with self.subTest(utterance):
                skill = self._skill(stored)
                data = {"utterance": utterance}
                if name:
                    data["list_name"] = name
                AlertSkill.handle_delete_list_entries(
                    skill, Message("test", data))
                getattr(skill, taken).assert_called_once()
                getattr(skill, skipped).assert_not_called()


if __name__ == "__main__":
    unittest.main()
