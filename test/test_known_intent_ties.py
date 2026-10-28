"""A gold utterance that ties at the matcher keeps the winner on record.

Several gold rows sit on a tie: padacioso scores two intent files the same
for the sentence and breaks the tie by pattern specificity, then by name.
"change my alarm to repeat every monday" fits change_repeat's
`change my {schedkind} to repeat every {repeat}` and reschedule_alert's
`change my {schedkind} to {time}` at the same confidence. The gold row
records the winner of this release. A padacioso release that breaks the tie
another way, or a template edit that adds a third contender, moves the
answer and no test says so.

`known_intent_ties.json` stores every gold utterance that ties, the intents
it ties between, and the winner the gold row records. Two things are
asserted, per locale that ships gold: every recorded utterance still
resolves to its recorded winner, and no gold utterance newly ties or ties
between a different set of intents. Removing a tie is expected and passes;
the record is then trimmed in the same commit.

The container is built the way the skill loads its resources: every
`.entity` file registered so a `{slot}` is bound to its value list, every
`<voc>` reference expanded, every `.intent` template added. Without the
entities `{mediaform}` and `{time}` both swallow "9 am" and 27 gold rows
read as ties that the running skill never sees.
"""
import json
import logging
from pathlib import Path

import pytest
from ovos_spec_tools.expansion import expand
from padacioso import IntentContainer

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locale"
GOLD_DIR = Path(__file__).parent / "end2end"
KNOWN = json.loads((Path(__file__).parent / "known_intent_ties.json").read_text(encoding="utf-8"))
GOLD_LANGS = sorted(p.stem.split("_", 2)[2] for p in GOLD_DIR.glob("golden_utterances_*.jsonl")
                    if (LOCALES / p.stem.split("_", 2)[2]).is_dir())


def _lines(path: Path):
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def build_container(lang: str) -> IntentContainer:
    locale = LOCALES / lang
    vocs = {}
    for sub, pattern in (("vocab", "*.voc"), ("entity", "*.entity")):
        for f in (locale / sub).glob(pattern):
            vocs[f.stem] = _lines(f)
    container = IntentContainer(fuzz=False)
    for f in sorted((locale / "entity").glob("*.entity")):
        container.add_entity(f.stem, _lines(f))
    for f in sorted((locale / "intent").glob("*.intent")):
        samples = []
        for line in _lines(f):
            try:
                samples.extend(expand(line, vocs))
            except Exception:
                samples.append(line)  # a malformed line is another test's business
        container.add_intent(f.stem, samples)
    return container


def gold_utterances(lang: str):
    path = GOLD_DIR / f"golden_utterances_{lang}.jsonl"
    return [json.loads(l)["utterance"] for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def tied_intents(container: IntentContainer, utterance: str):
    """The intents scoring the top confidence for *utterance*, sorted; one
    name when there is no tie."""
    matches = [m for m in container.calc_intents(utterance) if m and m.get("name")]
    if not matches:
        return []
    best = max(m["conf"] for m in matches)
    return sorted(m["name"] for m in matches if m["conf"] == best)


@pytest.fixture(scope="module", params=GOLD_LANGS)
def lang_and_container(request):
    logging.disable(logging.INFO)  # padacioso logs every tie it breaks
    try:
        yield request.param, build_container(request.param)
    finally:
        logging.disable(logging.NOTSET)


def test_every_recorded_tie_keeps_its_winner(lang_and_container):
    lang, container = lang_and_container
    moved = {}
    for utterance, record in KNOWN.get(lang, {}).items():
        winner = container.calc_intent(utterance).get("name")
        if winner != record["winner"]:
            moved[utterance] = (record["winner"], winner)
    assert not moved, (
        f"{lang}: the matcher now breaks these ties differently than the gold "
        f"row records (recorded -> now):\n  "
        + "\n  ".join(f"{u!r}: {was} -> {now}" for u, (was, now) in sorted(moved.items())))


def test_no_gold_utterance_ties_unrecorded(lang_and_container):
    lang, container = lang_and_container
    known = KNOWN.get(lang, {})
    new = {}
    for utterance in gold_utterances(lang):
        tied = tied_intents(container, utterance)
        if len(tied) < 2:
            continue
        if known.get(utterance, {}).get("tied") != tied:
            new[utterance] = tied
    assert not new, (
        f"{lang}: these gold utterances tie at the matcher and the tie is not on "
        f"record with this set of intents; record the winner in "
        f"known_intent_ties.json or change the templates so they do not tie:\n  "
        + "\n  ".join(f"{u!r} -> {t}" for u, t in sorted(new.items())))


def test_the_record_names_only_intents_that_exist():
    """A stale record (an intent renamed or removed) fails here, not silently."""
    for lang, records in KNOWN.items():
        shipped = {f.stem for f in (LOCALES / lang / "intent").glob("*.intent")}
        for utterance, record in records.items():
            unknown = [i for i in record["tied"] + [record["winner"]] if i not in shipped]
            assert not unknown, f"{lang} {utterance!r}: {unknown} is not an intent file"
            assert record["winner"] in record["tied"], f"{lang} {utterance!r}: winner not among tied"
