"""The skill reads its locale words through ovos-spec-tools.

The kab and pt-BR word files open with a "# machine ..." header. The skill's
own reader returned a file's first line, so {kind} was spoken as
"# machine translation from en-US, unvouched". translate() and
get_words_list() now load through ovos_spec_tools' LocaleResources, which
applies the OVOS-INTENT-2 common reader: blank and comment lines dropped.
"""
import os

import pytest
from ovos_spec_tools.resources import LocaleResources
from ovos_workshop.resource_files import SkillResources

from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.locale import (get_words_list, spoken_alert_type,
                                           translate)

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE = LocaleResources(os.path.join(SKILL_ROOT, "locale"))
KINDS = (AlertType.ALARM, AlertType.TIMER, AlertType.REMINDER, AlertType.EVENT)


@pytest.mark.parametrize("lang", ["kab", "pt-BR"])
def test_kind_renders_as_the_word_in_the_draft_locales(lang):
    resources = SkillResources(SKILL_ROOT, lang.lower())
    for alert_type in KINDS:
        kind = spoken_alert_type(alert_type, lang)
        text = resources.render_dialog("error_no_scheduled_kind",
                                       {"kind": kind})
        assert "#" not in kind and "machine" not in text, text
        assert kind == REFERENCE.load_dialog(alert_type.name.lower(), lang)[0]


def _words():
    root = os.path.join(SKILL_ROOT, "locale")
    for lang in sorted(os.listdir(root)):
        folder = os.path.join(root, lang, "dialog", "words")
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else ():
            if name.endswith(".dialog"):
                yield lang, name[:-len(".dialog")]


@pytest.mark.parametrize("lang, word", list(_words()))
def test_translate_is_the_reference_loaders_first_phrase(lang, word):
    assert translate(word, lang) == REFERENCE.load_dialog(word, lang)[0]


@pytest.mark.parametrize("lang", ["en-US", "pt-BR", "kab", "eu-ES"])
def test_a_voc_word_list_is_the_reference_expansion(lang):
    assert get_words_list("noise_words.voc", lang) == \
        REFERENCE.voc_list("noise_words", lang)
