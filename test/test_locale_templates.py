"""Validate that every locale resource template is well-formed."""
import os
import unittest

from ovos_spec_tools.expansion import expand

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_ROOT = os.path.join(REPO_ROOT, "locale")
EXTENSIONS = (".voc", ".intent", ".dialog", ".entity", ".rx")


class TestLocaleTemplates(unittest.TestCase):
    def test_all_templates_expand(self):
        failures = []
        for root, _, files in os.walk(LOCALE_ROOT):
            for fname in sorted(files):
                if not fname.endswith(EXTENSIONS):
                    continue
                path = os.path.join(root, fname)
                with open(path, encoding="utf-8") as f:
                    for lineno, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        try:
                            expand(line)
                        except Exception as e:
                            rel = os.path.relpath(path, REPO_ROOT)
                            failures.append(f"{rel}:{lineno}: {line!r} -> {e}")
        self.assertEqual(
            failures, [],
            "Malformed locale templates:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
