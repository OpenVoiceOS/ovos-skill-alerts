"""Render every dialog reached from a handled branch of __init__.py through
the skill's real en-US resource loader and assert the rendered text is not
just the raw dialog name (the fallback ovos-workshop returns when no .dialog
file exists for the requested locale) and, where slots are passed, that the
substituted value actually appears in the output.
"""
import ast
import os
import re
import unittest

from ovos_workshop.resource_files import SkillResources

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestDialogRendering(unittest.TestCase):
    def setUp(self):
        self.resources = SkillResources(SKILL_ROOT, "en-us")

    def _render(self, name, data=None):
        return self.resources.render_dialog(name, data or {})

    def test_error_no_script(self):
        text = self._render("error_no_script", {"kind": "reminder"})
        self.assertNotEqual(text, "error_no_script")
        self.assertIn("reminder", text)

    def test_error_same_priority(self):
        text = self._render("error_same_priority")
        self.assertNotEqual(text, "error_same_priority")
        self.assertTrue(text.strip())

    def test_media_type_changed(self):
        text = self._render("media_type_changed", {"old": "beep", "new": "chime"})
        self.assertNotEqual(text, "media_type_changed")
        self.assertIn("beep", text)
        self.assertIn("chime", text)

    def test_media_type_set(self):
        text = self._render("media_type_set", {"new": "chime"})
        self.assertNotEqual(text, "media_type_set")
        self.assertIn("chime", text)

    def test_property_changed_priority(self):
        text = self._render("property_changed_priority", {"num": 3})
        self.assertNotEqual(text, "property_changed_priority")
        self.assertIn("3", text)


class TestMediaAndPriorityDialogsPerLocale(unittest.TestCase):
    """The five dialogs this skill speaks about sounds and priority, in
    every locale that ships them.

    The loader answers with the dialog NAME when a locale has no file, so a
    missing file is not an error at runtime: the skill says
    "media_type_set" out loud. That is why each locale is asserted here and
    not only en-US, and why the slot value is asserted in the output: a
    translation that drops `{new}` renders without it and reports nothing.

    The locale list is READ FROM THE TREE, never written here. A locale that
    ships at least one of the five must ship all five; a locale that ships
    none is not this test's business. So the answer to sv-FI, which T-1775
    decides -- rewrite it in Finland-Swedish, or drop the directory -- does
    not turn this test red either way, and a locale added tomorrow is
    covered without an edit.

    There is no assertion that the render is not a comment line: the loader
    strips `#` lines before a phrase reaches the renderer, so it cannot
    happen. Probed both ways on this tree: a file whose first line is a
    comment renders its second line, and a comment-only file renders the
    bare dialog name, which the first assertion below already catches.
    """

    CASES = {
        "error_no_script": ({"kind": "reminder"}, ["reminder"]),
        "error_same_priority": ({}, []),
        "media_type_changed": ({"old": "beep", "new": "chime"},
                               ["beep", "chime"]),
        "media_type_set": ({"new": "chime"}, ["chime"]),
        "property_changed_priority": ({"num": 3}, ["3"]),
    }

    @classmethod
    def locales(cls):
        """Locales that ship any of the five, read from locale/."""
        root = os.path.join(SKILL_ROOT, "locale")
        found = []
        for lang in sorted(os.listdir(root)):
            dialogs = os.path.join(root, lang, "dialog")
            if not os.path.isdir(dialogs):
                continue
            if any(os.path.isfile(os.path.join(dialogs, f"{name}.dialog"))
                   for name in cls.CASES):
                found.append(lang)
        return found

    def test_every_locale_renders_all_five(self):
        locales = self.locales()
        self.assertIn("en-US", locales,
                      "the reference locale ships none of the five; the "
                      "locale reader is probably looking in the wrong place")
        for lang in locales:
            resources = SkillResources(SKILL_ROOT, lang.lower())
            for name, (data, expected) in self.CASES.items():
                with self.subTest(lang=lang, dialog=name):
                    text = resources.render_dialog(name, data)
                    self.assertNotEqual(
                        text, name,
                        f"locale/{lang} ships some of these five and not "
                        f"{name}.dialog; the skill would speak the dialog "
                        f"name out loud in that language")
                    self.assertTrue(text.strip())
                    for value in expected:
                        self.assertIn(
                            value, text,
                            f"locale/{lang}/{name}.dialog dropped a slot")


class TestEverySpokenDialogSlot(unittest.TestCase):
    """Every slot a spoken dialog uses is a key its call site passes.

    `alert_prenotification.dialog` held `{remimder}` in all 18 locales that
    ship it, and `_alert_prenotification` passes `reminder`. The renderer
    calls `line.format(**context)`, so the render raised
    `KeyError: 'remimder'`; `speak_dialog` does not guard it, and the
    prenotification said nothing in every language.

    Why this reads the file rather than rendering it: a `.dialog` holds
    several lines and the renderer picks ONE at random, so a bad slot on a
    single line fails only sometimes. Reading every line of every file is
    deterministic, and that is what makes this a guard rather than a flake.

    The call sites are read from the AST, so a dialog added tomorrow is
    covered with no edit here. A call site that builds its data dictionary
    at runtime cannot be read this way; those dialogs are named and skipped
    rather than guessed at.
    """

    SLOT = re.compile(r"\{([^{}]+)\}")

    @staticmethod
    def _call_sites():
        """({dialog: keys}, {dialogs whose data is computed})."""
        tree = ast.parse(open(os.path.join(SKILL_ROOT, "__init__.py"),
                              encoding="utf-8").read())
        known, computed = {}, set()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", "") == "speak_dialog"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            name = node.args[0].value
            data = node.args[1] if len(node.args) > 1 else next(
                (kw.value for kw in node.keywords if kw.arg == "data"), None)
            if data is None:
                known.setdefault(name, set())
            elif (isinstance(data, ast.Dict)
                  and all(isinstance(k, ast.Constant) for k in data.keys)):
                known.setdefault(name, set()).update(
                    k.value for k in data.keys)
            else:
                computed.add(name)
        return known, computed

    def test_no_dialog_line_uses_a_slot_its_caller_never_passes(self):
        known, computed = self._call_sites()
        checkable = {n: k for n, k in known.items() if n not in computed}
        self.assertGreater(len(checkable), 40,
                           "the call-site reader found almost nothing; it is "
                           "probably no longer reading __init__.py")
        offenders = []
        for name, keys in sorted(checkable.items()):
            path = os.path.join(SKILL_ROOT, "locale", "en-US", "dialog",
                                f"{name}.dialog")
            if not os.path.isfile(path):
                offenders.append(f"{name}.dialog: en-US ships no such file")
                continue
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    for slot in self.SLOT.findall(line):
                        # a typed slot declares {type:name}; the name binds
                        if slot.split(":")[-1] not in keys:
                            offenders.append(
                                f"{name}.dialog:{number}: uses "
                                f"{{{slot}}}, and the call site passes "
                                f"{sorted(keys)}")
        self.assertEqual([], offenders, "\n".join([""] + offenders))


if __name__ == "__main__":
    unittest.main()
