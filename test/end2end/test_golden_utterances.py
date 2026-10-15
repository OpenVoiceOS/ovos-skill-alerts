"""Golden rows in every locale route to their intent on the m2v pipeline.

For each ``golden_utterances_<lang>.jsonl`` in this directory, one MiniCroft
loads the real skill in that language on the m2v prototype pipeline, the
model2vec engine built at boot from the skill's own ``.intent``, ``.entity``
and ``.blacklist`` files. Each row's utterance goes through that pipeline's
high, medium and low tiers in order, and the row passes when the first tier to
match names its ``intent_label``. The test prints the tier that matched each
row. The engine embeds the utterance, so a row that no template spells out
word for word still matches when it means the same thing.

Each locale must match at least ``MIN_MATCH_RATE`` of its rows, and every
intent with rows in the locale must match at least
``MIN_MATCHED_ROWS_PER_INTENT`` of them, so a locale cannot lose a whole
intent and still pass on the rate. ``GOLDEN_INTENT_GAPS`` names the intents
that m2v already misses for every row of a locale, and ``GOLDEN_LOCALE_GAPS``
names the locales whose rate stays below the gate. All rows run, including
rows marked ``needs_manual`` or ``machine_generated``, and the test prints
every row that misses with the intent that matched instead.

Each ``negative_utterances_<lang>.jsonl`` holds requests for other skills.
They run on the same pipeline and must match no intent of this skill. A claim
that m2v makes in every measured run is listed by name in
``NEGATIVE_KNOWN_CLAIMS`` and tolerated; any other claim fails the locale.
"""
import json
from collections import Counter
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovoscope import M2V_PUBLISHED_MODEL, get_m2v_minicroft
from ovoscope.golden_minicroft import warm_m2v_models

SKILL_ID = "ovos-skill-alerts.openvoiceos"
M2V_PROTOTYPE = "ovos-m2v-prototype-pipeline"
TIERS = ("high", "medium", "low")
# m2v gives some rows a different answer on each boot, so the test gates on
# the share of rows that match per locale, not on each row.
# Natural rows with no near copies of template lines measure 58-86% per locale
# on the m2v prototype pipeline.
MIN_MATCH_RATE = 0.6
MIN_MATCHED_ROWS_PER_INTENT = 1
# Intents for which m2v matched none of the locale's rows in two measured
# runs. The floor skips a listed intent. Any other intent with no matched row
# fails the locale. Where the rows go in the two runs:
# - change_until: reschedule_alert, change_media_properties, create_alarm,
#   list_alerts and change_priority, or no match.
# - create_alarm: da-DK list_alerts; es-CO change_media_properties; fa-IR
#   reschedule_alert, create_reminder and change_media_properties.
# - create_timer: de-DE and sv-FI timer_status; fa-IR change_until and
#   list_alerts; kab change_media_properties, create_list and create_reminder;
#   pl-PL list_alerts, change_media_properties and change_priority.
# - change_repeat: change_media_properties, and fi-FI cancel_alert.
# - reschedule_alert: cs-CZ list_alerts; fa-IR change_repeat and change_until;
#   hu-HU create_event and timer_status; and change_media_properties.
# - delete_list and delete_list_entries: query_list_entries, delete_list,
#   delete_list_entries, create_list and missed_alerts.
# - kab missed_alerts: change_media_properties.
GOLDEN_INTENT_GAPS = {
    "ca-ES": ("change_until",),
    "cs-CZ": ("change_until", "reschedule_alert"),
    "da-DK": ("create_alarm", "delete_list_entries"),
    "de-DE": ("create_timer",),
    "es-CO": ("create_alarm",),
    "fa-IR": ("create_alarm", "create_timer", "reschedule_alert"),
    "fi-FI": ("change_repeat",),
    "hu-HU": ("reschedule_alert",),
    "kab": ("create_timer", "missed_alerts"),
    "pl-PL": ("change_repeat", "change_until", "create_timer", "delete_list_entries"),
    "ru-RU": ("change_until", "delete_list", "delete_list_entries"),
    "sv-FI": ("create_timer",),
}
# Locales whose rate stays below MIN_MATCH_RATE in two measured runs. For a
# listed locale the rate check is a non-strict xfail that prints the measured
# rate; the per-intent floor still applies.
GOLDEN_LOCALE_GAPS = {
    "pl-PL": "58.2% and 59.5% of rows match in two runs; the pl-PL templates are "
             "unvouched machine drafts, and a Polish speaker must write lines",
}
END2END_DIR = Path(__file__).parent
# With only this skill loaded, the published m2v model claims every fa-IR and
# ru-RU request for another skill at the medium or low tier.
NEGATIVE_ENGINE_GAPS = {
    lang: f"m2v claims every {lang} request for another skill at the medium and low tiers"
    for lang in ("fa-IR", "ru-RU")
}
# Requests for other skills that m2v gave to an alerts intent in both of two
# local runs or in a CI run, with the intents it picked. A listed claim is
# allowed, not required: the row may also match nothing.
NEGATIVE_KNOWN_CLAIMS = {
    "ca-ES": {
        "quina és la meva adreça ip": ("reschedule_alert",),
    },
    "cs-CZ": {
        "jak se píše slovo nezbytný": ("change_media_properties",),
        "jaká je moje ip adresa": ("list_alerts",),
        "jaké bude zítra počasí": ("list_alerts",),
        "kolik je hodin": ("timer_status",),
        "pusť nějakou jazzovou hudbu": ("change_media_properties",),
        "řekni mi vtip": ("list_alerts",),
    },
    "da-DK": {
        "hvad er min ip adresse": ("query_list_entries",),
    },
    "en-US": {
        "play some jazz music": ("create_alarm",),
    },
    "eu-ES": {
        "jarri bolumena ehuneko berrogeita hamarrean": ("dav_sync",),
        "zein da nire ip helbidea": ("list_alerts",),
        "zer eguraldi egingo du bihar": ("cancel_alert", "list_alerts"),
        "zer ordu da": ("timer_status",),
    },
    "fi-FI": {
        "aseta äänenvoimakkuus viiteenkymmeneen prosenttiin": ("change_media_properties",),
        "millainen sää huomenna on": ("change_media_properties",),
        "miten tavataan sana välttämätön": ("change_media_properties",),
    },
    "gl-ES": {
        "cal é o meu enderezo ip": ("list_alerts",),
    },
    "hu-HU": {
        "hogyan kell betűzni azt hogy szükséges": ("list_alerts",),
        "hány óra van": ("timer_status",),
        "játssz valami jazz zenét": ("list_alerts",),
        "mi az ip címem": ("list_alerts",),
        "milyen idő lesz holnap": ("timer_status",),
        "állítsd a hangerőt ötven százalékra": ("change_media_properties",),
    },
    "it-IT": {
        "raccontami una barzelletta": ("query_list_entries",),
    },
    "kab": {
        "acḥal n ssaɛa i yellan": ("calendar_list",),
        "amek ara yili lḥal azekka": ("change_media_properties",),
        "ini-yi-d yiwet n tqeṣṣiṭ n uḍḥak": ("create_reminder",),
        "sali taɣect ɣer xemsin di miya": ("change_media_properties",),
    },
    "nl-NL": {
        "wat is mijn ip-adres": ("list_alerts",),
    },
    "pl-PL": {
        "jak się pisze słowo konieczny": ("cancel_alert", "list_alerts", "timer_status"),
        "jaka będzie jutro pogoda": ("create_event",),
        "jaki jest mój adres ip": ("cancel_alert",),
        "ustaw głośność na pięćdziesiąt procent": ("list_alerts",),
        "włącz muzykę jazzową": ("change_media_properties",),
    },
    "pt-BR": {
        "qual é o meu endereço ip": ("list_alerts",),
    },
    "pt-PT": {
        "qual é o meu endereço ip": ("list_alerts",),
    },
    "sv-FI": {
        "hurdant väder blir det i morgon": ("timer_status",),
        "spela lite jazzmusik": ("change_media_properties",),
        "vad är min ip-adress": ("query_list_entries",),
    },
    "sv-SE": {
        "hur blir vädret i morgon": ("timer_status",),
        "spela lite jazzmusik": ("change_media_properties",),
        "vad är min ip-adress": ("query_list_entries",),
    },
}


def _rows_by_lang(prefix):
    rows = {}
    for path in sorted(END2END_DIR.glob(f"{prefix}_*.jsonl")):
        lang = path.stem.removeprefix(f"{prefix}_")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                assert row["lang"] == lang, f"{path.name}:{number} has lang {row['lang']!r}"
                rows.setdefault(lang, []).append(row)
    return rows


ROWS = _rows_by_lang("golden_utterances")
NEGATIVE_ROWS = _rows_by_lang("negative_utterances")


def _first_match(engine, utterance, lang):
    """Return ``(tier, intent)`` for the first tier that matches, or ``(None, None)``."""
    message = Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang}, {"lang": lang})
    for tier in TIERS:
        match = getattr(engine, f"match_{tier}")([utterance], lang, message)
        if match:
            return tier, match.match_type
    return None, None


def _match_all(lang, rows):
    """Boot the skill on m2v in ``lang`` and return ``(tier, intent)`` for each row."""
    minicroft = get_m2v_minicroft([SKILL_ID], model=M2V_PUBLISHED_MODEL,
                                  lang=lang, classifier=False)
    try:
        warm_m2v_models(minicroft)
        engine = minicroft.intents.pipeline_plugins[M2V_PROTOTYPE]
        return [_first_match(engine, row["utterance"], lang) for row in rows]
    finally:
        minicroft.stop()


@pytest.mark.timeout(900)
@pytest.mark.parametrize("lang", sorted(ROWS))
def test_golden_rows_match_their_intent(lang):
    rows = ROWS[lang]
    misses, lines = [], []
    hits_per_intent = Counter()
    for row, (tier, got) in zip(rows, _match_all(lang, rows)):
        lines.append(f"{tier}: {row['utterance']!r} -> {got}")
        if got == f"{SKILL_ID}:{row['intent_label']}":
            hits_per_intent[row["intent_label"]] += 1
        else:
            misses.append(f"{row['utterance']!r}: expected {row['intent_label']}, got {got}")
    rate = 1 - len(misses) / len(rows)
    print(f"[{lang}] {rate:.1%} of {len(rows)} rows match", *lines, "misses:", *misses,
          sep="\n  ")
    gaps = set(GOLDEN_INTENT_GAPS.get(lang, ()))
    lost = sorted({row["intent_label"] for row in rows
                   if hits_per_intent[row["intent_label"]] < MIN_MATCHED_ROWS_PER_INTENT}
                  - gaps)
    report = [f"{label}: {[row['utterance'] for row in rows if row['intent_label'] == label]}"
              for label in lost]
    assert not lost, (
        f"[{lang}] intents with fewer than {MIN_MATCHED_ROWS_PER_INTENT} matched row:\n  "
        + "\n  ".join(report)
    )
    if rate < MIN_MATCH_RATE and lang in GOLDEN_LOCALE_GAPS:
        pytest.xfail(f"[{lang}] {rate:.1%} of rows match: {GOLDEN_LOCALE_GAPS[lang]}")
    assert rate >= MIN_MATCH_RATE, (
        f"[{lang}] {rate:.1%} of rows match, below {MIN_MATCH_RATE:.0%}:\n  " + "\n  ".join(misses)
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("lang", [
    pytest.param(lang, marks=pytest.mark.xfail(reason=NEGATIVE_ENGINE_GAPS[lang]))
    if lang in NEGATIVE_ENGINE_GAPS else lang
    for lang in sorted(NEGATIVE_ROWS)
])
def test_negative_rows_match_no_skill_intent(lang):
    rows = NEGATIVE_ROWS[lang]
    known = NEGATIVE_KNOWN_CLAIMS.get(lang, {})
    claims, unknown = [], []
    for row, (tier, got) in zip(rows, _match_all(lang, rows)):
        if got and got.startswith(f"{SKILL_ID}:"):
            claim = f"{row['utterance']!r}: matched {got} at {tier}"
            claims.append(claim)
            if got.removeprefix(f"{SKILL_ID}:") not in known.get(row["utterance"], ()):
                unknown.append(claim)
    print(f"[{lang}] {len(rows) - len(claims)} of {len(rows)} negative rows stay out of the skill,"
          f" {len(unknown)} unknown claims", *claims, sep="\n  ")
    assert not unknown, f"[{lang}] claims not in NEGATIVE_KNOWN_CLAIMS:\n  " + "\n  ".join(unknown)


def test_every_shipping_locale_has_a_golden_file():
    golden = {p.stem.split("_", 2)[2] for p in END2END_DIR.glob("golden_utterances_*.jsonl")}
    locale_root = END2END_DIR.parents[1] / "locale"
    shipping = {d.name for d in locale_root.iterdir() if d.is_dir() and any(d.rglob("*.intent"))}
    assert golden == shipping, f"golden files {sorted(golden ^ shipping)} differ from shipping locales"
