"""Multilingual golden-utterance end-to-end coverage for ovos-skill-alerts.

test_intents_en_us.py only exercises en-US; every other locale under
locale/ ships real adapt vocab (create.voc / alarm.voc / timer.voc /
reminder.voc / cancel.voc / query.voc, etc.) that was completely
untested end-to-end. Alerts is a big skill (30+ adapt intents), so this
suite keeps scope tractable: it covers only the primary alarm/timer/
reminder-creation + cancel + query intents (CreateAlarm, CreateTimer,
CreateReminder, CancelAlert, ListAlerts), ~15 rows per locale, across
every locale that has real (non-metadata-only) vocab content on dev.

Row construction: ovos-skill-alerts' adapt intents (see __init__.py
IntentBuilder(...).require(...) calls) are presence-only matches over
required vocab files, not sentence templates -- there is no .intent file
to expand() for these intents. So each row is built by expanding every
line of the locale's own required .voc file(s) for that intent via
ovos_spec_tools.expand() (to resolve any (a|b) alternatives within a
single vocab line) and concatenating one sample from each required
vocab file. This is a direct, mechanical derivation from the skill's
own existing locale content -- no drafted or translated glue words are
introduced; the "sentences" read as adapt-vocab keyword concatenations
rather than fluent native prose, which matches how the adapt pipeline
actually matches them (bag-of-required-vocab, order-independent).

One shared MiniCroft is booted with en-US as the primary language and
every covered locale as a secondary_lang (ovoscope>=1.6.5a1 /
padacioso>=2.2.3a1, cross-language detach fix).

Capture ends at ``mycroft.skill.handler.start``: several of these
handlers call get_response() for a missing time/duration follow-up
(see test_intents_en_us.py docstring), which deadlocks on a bare
MiniCroft/FakeBus; the intent-routing assertion under test fires before
that.
"""
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-alerts.openvoiceos"

_PIPELINE = [
    "ovos-adapt-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-adapt-pipeline-plugin-low",
]

_IGNORE = [
    "speak",
    "ovos.utterance.speak",
    "gui.page.show",
    "skill.converse.get_response",
    "mycroft.audio.play_sound",
    "mycroft.scheduler.schedule_event",
    "mycroft.scheduler.remove_event",
]

END2END_DIR = Path(__file__).parent

LANGS = [
    "ca-ES", "cs-CZ", "da-DK", "de-DE", "es-ES", "eu-ES", "fr-FR",
    "gl-ES", "hu-HU", "it-IT", "nl-NL", "pl-PL", "pt-PT", "ru-RU",
    "sv-FI", "sv-SE",
]

CROSS_LANG_NEGATIVES = [
    ("Wecker stellen", "en-US", "german utterance in an english session"),
    ("set an alarm", "de-DE", "english utterance in a german session"),
    ("annuler la minuterie", "es-ES", "french utterance in a spanish session"),
    ("play some music", "de-DE", "other-skill (music) phrasing, german session"),
    ("what's the weather", "fr-FR", "other-skill (weather) phrasing, french session"),
]


def _candidates(skill_id: str, intent_label: str) -> set:
    return {f"{skill_id}:{intent_label}"}


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _as_param(row):
    tag = "tier2" if row.get("machine_generated") else "tier1"
    return pytest.param(row, id=f"{row['lang']}-{tag}-{row['intent_label']}-{row['utterance']}")


GOLDEN_ROWS = [_as_param(r) for r in ALL_ROWS]


@pytest.fixture(scope="module")
def minicroft():
    # get_minicroft's default max_wait (60s) is tuned for the plain test
    # job; under coverage instrumentation, booting one MiniCroft with this
    # many secondary_langs (16) reliably needs more than 60s. Bump it well
    # past the coverage-job boot time observed in CI rather than trim
    # locales or add extra instances.
    mc = get_minicroft([SKILL_ID], secondary_langs=LANGS, max_wait=300)
    yield mc
    mc.stop()


def _types(mc, text, lang, session_id):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(_PIPELINE)
    session.blacklisted_intents = []
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["mycroft.skill.handler.start"],
        ignore_messages=_IGNORE,
    )
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


# Real locale-content defects reproduced and fixed in-place during this
# pass (red-before/green-after verified for each), not xfailed -- every
# one was the *same* class of bug: a single word copy/paste-duplicated
# into an unrelated vocab file, making adapt's require()/one_of() presence
# match ambiguous between two intents on a short 2-token utterance built
# purely from that locale's own content:
#   - de-DE locale/de-DE/vocab/timer.voc: "erinnerungen" (="reminders")
#     duplicated a reminder.voc word, shadowing CreateReminder with
#     CreateTimer. Removed from timer.voc.
#   - cs-CZ locale/cs-CZ/vocab/query.voc: "mám" (="I have") duplicated the
#     create.voc entry "Mám", shadowing CreateAlarm/CreateReminder with
#     ListAlerts. Removed the query.voc duplicate (create.voc's is the
#     canonical slot, matching the en-US precedent where "i have" lives
#     only in create.voc).
#   - it-IT locale/it-IT/vocab/query.voc: same pattern, "ho" (="I have")
#     duplicated the create.voc entry "Ho". Removed the query.voc
#     duplicate.
#   - sv-SE locale/sv-SE/vocab/change.voc: "avbryta" (="cancel/abort")
#     duplicated the cancel.voc entry, shadowing CancelAlert with
#     ChangeProperties/RescheduleAlert. "avbryta" does not mean
#     "postpone/reschedule" (change.voc's actual concept, cf. en-US's
#     adjust/extend/move/postpone/reschedule/shift); removed from
#     change.voc.
#
# No unfixable (would-require-new-vocabulary) routing races were left
# over after these four fixes -- the full suite is green without any
# xfails. This dict is kept, empty, as the landing spot for any future
# genuine engine-level race that can't be fixed by removing a misplaced
# vocab entry.
KNOWN_BUGS = {}


@pytest.mark.timeout(300)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance_multilang(minicroft, row):
    candidates = _candidates(SKILL_ID, row["intent_label"])
    types = _types(minicroft, row["utterance"], row["lang"], f"golden-{_golden_id(row)}")
    matched = any(t in candidates for t in types)
    bug_key = (row["lang"], row["utterance"])
    if bug_key in KNOWN_BUGS and not matched:
        pytest.xfail(reason=f"known-bug: {KNOWN_BUGS[bug_key]}")
    if row.get("machine_generated") and not matched:
        pytest.xfail(reason="coverage-gap (machine-drafted, pending native validation)")
    assert matched, (
        f"[{row['lang']}] {row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )


KNOWN_NEGATIVE_BUGS = {}


@pytest.mark.timeout(300)
@pytest.mark.parametrize("negative", CROSS_LANG_NEGATIVES, ids=lambda n: f"{n[1]}-{n[0]}")
def test_cross_language_negative(minicroft, negative):
    text, lang, _why = negative
    types = _types(minicroft, text, lang, f"negative-{lang}-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    bug_key = (lang, text)
    if bug_key in KNOWN_NEGATIVE_BUGS and claimed:
        pytest.xfail(reason=f"known-bug: {KNOWN_NEGATIVE_BUGS[bug_key]}")
    assert not claimed, f"[{lang}] {text!r} was incorrectly claimed by {SKILL_ID}"
