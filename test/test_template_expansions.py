"""Every locale's intent templates expand to sentences that one intent owns.

The intent classifier is trained on the sentences these templates expand to.
A sentence that two intents both produce is a label conflict, and a doubled
word ("el el despertador") is never a sentence a person says.
"""
import itertools
import os
import re

import pytest

LOCALE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "locale")
LOCALES = sorted(d for d in os.listdir(LOCALE_DIR)
                 if os.path.isdir(os.path.join(LOCALE_DIR, d, "intent")))

_GROUP = re.compile(r"\(([^()\[\]]*)\)|\[([^\[\]()]*)\]")
_SLOT = re.compile(r"\{(\w+)(?::\w+)?\}")
_DOUBLED = re.compile(r"(?<![\w·])([\w·]{2,}) \1(?![\w·])")


def _alternatives(template):
    match = _GROUP.search(template)
    if not match:
        return [template]
    options = match.group(1).split("|") if match.group(1) is not None \
        else match.group(2).split("|") + [""]
    return [text for option in options for text in _alternatives(
        template[:match.start()] + option + template[match.end():])]


def _lines(path):
    with open(path, encoding="utf8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def _entity(lang, name):
    path = os.path.join(LOCALE_DIR, lang, "entity", f"{name}.entity")
    return _lines(path) if os.path.exists(path) else None


def _expand(lang, intent):
    sentences = set()
    path = os.path.join(LOCALE_DIR, lang, "intent", f"{intent}.intent")
    for line in _lines(path):
        for text in _alternatives(line):
            slots = _SLOT.findall(text)
            text = re.sub(r"\{(\w+):\w+\}", r"{\1}", text)
            values = [_entity(lang, s) or ["{" + s + "}"] for s in slots]
            for combo in itertools.product(*values):
                filled = text
                for slot, value in zip(slots, combo):
                    filled = filled.replace("{" + slot + "}", value, 1)
                sentences.add(" ".join(filled.lower().split()))
    return sentences


@pytest.fixture(scope="module")
def expansions():
    cache = {}

    def get(lang):
        if lang not in cache:
            names = [f[:-len(".intent")] for f in os.listdir(
                os.path.join(LOCALE_DIR, lang, "intent"))
                if f.endswith(".intent")]
            cache[lang] = {n: _expand(lang, n) for n in names}
        return cache[lang]
    return get


@pytest.mark.parametrize("lang", LOCALES)
def test_no_sentence_is_expanded_by_two_intents(lang, expansions):
    owners = {}
    for intent, sentences in expansions(lang).items():
        for sentence in sentences:
            owners.setdefault(sentence, []).append(intent)
    shared = {s: o for s, o in owners.items() if len(o) > 1}
    assert not shared, sorted(shared.items())[:10]


@pytest.mark.parametrize("lang", LOCALES)
def test_no_expansion_repeats_a_word(lang, expansions):
    repeated = sorted(s for sentences in expansions(lang).values()
                      for s in sentences if _DOUBLED.search(s))
    assert not repeated, repeated[:10]


def test_english_expansions_agree_in_article_and_number(expansions):
    singular = "(?:alarm|timer|countdown|reminder|event|appointment|alert)"
    bad = re.compile(r"\ba (?=[aeiou])|\ban (?=[^aeiou{\s])(?!hour)"
                     r"|\b(?:all|all my|all the) "
                     r"(?:(?:upcoming|pending|stored|saved|scheduled) )?"
                     + singular + r"(?!s|\w| clock)")
    flagged = sorted(s for sentences in expansions("en-US").values()
                     for s in sentences if bad.search(s))
    assert not flagged, flagged[:10]


@pytest.mark.parametrize("sentence, intent", [
    ("cancel my alarms", "cancel_alert"),
    ("cancel all my alarms and all my timers", "cancel_alert"),
    ("show me all my alarms", "list_alerts"),
    ("show me my alarm", "list_alerts"),
    ("set my alarm to play a podcast", "change_media_properties"),
    ("change my timer to play the news", "change_media_properties"),
    ("set an alarm with an audiobook", "create_alarm"),
    ("set a music alarm", "create_alarm"),
    ("wake me up with a podcast", "create_alarm"),
    ("extend my alarm to last until {duration}", "change_until"),
    ("move my alarms to {date}", "reschedule_alert"),
    ("did i miss alarms", "missed_alerts"),
    ("what alarm did i miss", "missed_alerts"),
    ("sync my calendar and events", "dav_sync"),
])
def test_english_phrasings_keep_their_owner(sentence, intent, expansions):
    assert sentence in expansions("en-US")[intent]
