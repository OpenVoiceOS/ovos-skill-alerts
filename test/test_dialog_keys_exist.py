"""Dialog resources: every dialog key the skill names exists in every locale,
the locales hold the same dialog files as en-US, and the list-selection prompt
renders the entry count in every phrase of every locale."""
import ast
import glob
import os
import unittest

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_ROOT = os.path.join(SKILL_ROOT, "locale")


def locales():
    return sorted(n for n in os.listdir(LOCALE_ROOT)
                  if os.path.isdir(os.path.join(LOCALE_ROOT, n)))


def dialog_names(lang):
    """Dialog basenames of one locale, words/ files included."""
    root = os.path.join(LOCALE_ROOT, lang, "dialog")
    return {os.path.relpath(path, root)[:-len(".dialog")]
            for path in glob.glob(os.path.join(root, "**", "*.dialog"),
                                  recursive=True)}


SPEAKING_CALLS = {"speak_dialog", "get_response", "ask_yesno",
                  "ask_for_prenotification"}


def parsed_sources():
    sources = [os.path.join(SKILL_ROOT, "__init__.py")]
    sources += glob.glob(os.path.join(SKILL_ROOT, "util", "**", "*.py"),
                         recursive=True)
    for path in sources:
        with open(path, encoding="utf8") as handle:
            yield ast.parse(handle.read())


def is_string(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def string_literals():
    """Every string literal in the skill's Python files.

    This finds keys held in variables, conditional expressions and helper
    arguments, but only those that match an en-US dialog name.
    """
    return {node.value for tree in parsed_sources() for node in ast.walk(tree)
            if is_string(node)}


def called_keys():
    """The literal first argument of every speaking call.

    This finds a key that has no file in any locale, which a match against
    en-US names cannot.
    """
    keys = set()
    for tree in parsed_sources():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else getattr(func, "id", ""))
            if name in SPEAKING_CALLS and is_string(node.args[0]):
                keys.add(node.args[0].value)
    return keys


def spoken_keys():
    return sorted((string_literals() & dialog_names("en-US")) | called_keys())


class TestDialogResources(unittest.TestCase):
    def test_locale_list_is_read_from_the_tree(self):
        self.assertGreater(len(locales()), 15)

    def test_every_named_key_exists_in_every_locale(self):
        keys = spoken_keys()
        self.assertGreater(len(keys), 80, "the literal scan found too few keys")
        missing = [f"{lang}/{key}" for lang in locales() for key in keys
                   if key not in dialog_names(lang)]
        self.assertEqual([], missing)

    def test_every_en_us_dialog_exists_in_every_locale(self):
        reference = dialog_names("en-US")
        missing = [f"{lang}/{key}" for lang in locales()
                   for key in sorted(reference - dialog_names(lang))]
        self.assertEqual([], missing)

    def test_choose_between_is_a_scanned_key(self):
        self.assertIn("alert_list_choose_between", spoken_keys())

    def test_choose_between_renders_the_count_in_every_phrase(self):
        for lang in locales():
            path = os.path.join(LOCALE_ROOT, lang, "dialog",
                                "alert_list_choose_between.dialog")
            with open(path, encoding="utf8") as handle:
                phrases = [line.strip() for line in handle
                           if line.strip() and not line.startswith("#")]
            self.assertGreaterEqual(len(phrases), 1, lang)
            for phrase in phrases:
                with self.subTest(lang=lang, phrase=phrase):
                    text = phrase.format(length=3)
                    self.assertIn("3", text)
                    self.assertFalse(text.startswith("#"))
