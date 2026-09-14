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


if __name__ == "__main__":
    unittest.main()
