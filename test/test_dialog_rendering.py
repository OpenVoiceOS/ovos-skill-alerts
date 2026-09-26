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


def locale_dirs():
    """Every locale directory the tree ships, read from the tree.

    Written out as a literal, this list goes stale silently: a locale added
    by a translation PR is simply never asserted, and the suite still reports
    all green. `locale/` is the only source that cannot drift from what ships.
    """
    root = os.path.join(SKILL_ROOT, "locale")
    return sorted(name for name in os.listdir(root)
                  if os.path.isdir(os.path.join(root, name)))


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
    # kab is a stub locale: it ships 5 of the 122 dialog files en-US ships, and
    # none of the five below. It is named here rather than skipped by a
    # "does the file exist" test, because a missing file is the very defect
    # this class catches -- the loader answers with the dialog NAME, so the
    # skill says "media_type_set" out loud. Naming it keeps the gap visible
    # and keeps every other locale asserted.
    STUB_LOCALES = ("kab",)

    @property
    def LOCALES(self):
        return [l for l in locale_dirs() if l not in self.STUB_LOCALES]

    def test_the_stub_locale_list_is_still_accurate(self):
        """Fails when kab grows the five files, or another locale loses them.

        Without this the tuple above is an unchecked exemption: a locale added
        to it silently stops being asserted, and kab filling in never removes
        it from it.
        """
        stubs = tuple(
            lang for lang in locale_dirs()
            if not all(os.path.isfile(os.path.join(
                SKILL_ROOT, "locale", lang, "dialog", f"{name}.dialog"))
                for name in self.CASES))
        self.assertEqual(
            self.STUB_LOCALES, stubs,
            f"locales missing one of {sorted(self.CASES)} are now {stubs}; "
            f"set STUB_LOCALES to that in the same commit that changes which "
            f"locales ship them")

    def test_every_locale_renders_all_five(self):
        self.assertGreater(len(self.LOCALES), 15,
                           "the locale list collapsed; it is no longer being "
                           "read from the tree")
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

    # The call sites below build their data dictionary at runtime, so the AST
    # reader cannot know which keys they pass and the slot check skips them.
    # They are named here for the same reason STUB_LOCALES is: an unchecked
    # skip that nothing watches grows silently, and a dialog added to it stops
    # being covered without anybody deciding that.
    COMPUTED_DATA_DIALOGS = (
        "alert_rescheduled_end",
        "alert_rescheduled_repeat",
        "list_alert_missed",
        "list_alert_w_duration",
        "list_alert_wo_duration",
        "timer_status",
    )

    def test_the_computed_data_dialog_list_is_still_accurate(self):
        """Fails when a call site starts or stops building its data at runtime.

        Shrinking is as much a change as growing: a dialog that becomes
        readable should join the slot check, not stay exempt.
        """
        _, computed = self._call_sites()
        self.assertEqual(
            self.COMPUTED_DATA_DIALOGS, tuple(sorted(computed)),
            "the dialogs whose data is built at runtime are now "
            f"{tuple(sorted(computed))}; set COMPUTED_DATA_DIALOGS to that in "
            "the same commit that changes the call site")

    def test_no_dialog_line_uses_a_slot_its_caller_never_passes(self):
        known, computed = self._call_sites()
        checkable = {n: k for n, k in known.items() if n not in computed}
        self.assertGreater(len(checkable), 40,
                           "the call-site reader found almost nothing; it is "
                           "probably no longer reading __init__.py")
        offenders = []
        for name, keys in sorted(checkable.items()):
            if not os.path.isfile(os.path.join(SKILL_ROOT, "locale", "en-US",
                                               "dialog", f"{name}.dialog")):
                offenders.append(f"{name}.dialog: en-US ships no such file")
                continue
            # Every locale that ships the file, not en-US alone. The slot
            # typo this guards for lived in all 18 locales that shipped
            # alert_prenotification.dialog, and a locale is where a
            # translation pass introduces the next one: #274 added 25
            # machine-translated dialog files across five unvouched locales
            # an hour before #279. Reading en-US alone, the guard reports
            # "1 passed" with {remimder} sitting in pl-PL.
            for lang in locale_dirs():
                path = os.path.join(SKILL_ROOT, "locale", lang, "dialog",
                                    f"{name}.dialog")
                if not os.path.isfile(path):
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
                                    f"{lang}/{name}.dialog:{number}: uses "
                                    f"{{{slot}}}, and the call site passes "
                                    f"{sorted(keys)}")
        self.assertEqual([], offenders, "\n".join([""] + offenders))


if __name__ == "__main__":
    unittest.main()
