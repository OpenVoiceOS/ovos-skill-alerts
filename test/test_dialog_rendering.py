"""Render every dialog reached from a handled branch of __init__.py through
the skill's real en-US resource loader and assert the rendered text is not
just the raw dialog name (the fallback ovos-workshop returns when no .dialog
file exists for the requested locale) and, where slots are passed, that the
substituted value actually appears in the output.
"""
import os
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
    """

    CASES = {
        "error_no_script": ({"kind": "reminder"}, ["reminder"]),
        "error_same_priority": ({}, []),
        "media_type_changed": ({"old": "beep", "new": "chime"},
                               ["beep", "chime"]),
        "media_type_set": ({"new": "chime"}, ["chime"]),
        "property_changed_priority": ({"num": 3}, ["3"]),
    }
    LOCALES = ["en-US", "cs-CZ", "hu-HU", "pl-PL", "ru-RU", "sv-FI"]

    def test_every_locale_renders_all_five(self):
        for lang in self.LOCALES:
            resources = SkillResources(SKILL_ROOT, lang.lower())
            for name, (data, expected) in self.CASES.items():
                with self.subTest(lang=lang, dialog=name):
                    text = resources.render_dialog(name, data)
                    self.assertNotEqual(
                        text, name,
                        f"locale/{lang} has no {name}.dialog the loader can "
                        f"read; the skill would speak the dialog name")
                    self.assertTrue(text.strip())
                    self.assertFalse(
                        text.lstrip().startswith("#"),
                        f"locale/{lang}/{name}.dialog rendered its comment "
                        f"line: {text!r}")
                    for value in expected:
                        self.assertIn(
                            value, text,
                            f"locale/{lang}/{name}.dialog dropped a slot")


if __name__ == "__main__":
    unittest.main()
