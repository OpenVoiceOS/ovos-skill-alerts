"""Every golden row in every locale names the intent the skill matches.

For each ``golden_utterances_<lang>.jsonl`` in this directory, one MiniCroft
loads the real skill in that language, and each row's utterance goes to the
padacioso container that the skill registers its ``.intent`` templates into.
The test asserts that the container names the row's ``intent_label``.

All rows run, including rows marked ``needs_manual`` or
``machine_generated``: a row that no template matches is a template gap or a
mis-labelled row, and the failure says which intent matched instead.
"""
import json
from pathlib import Path

import pytest
from ovoscope import get_minicroft

SKILL_ID = "ovos-skill-alerts.openvoiceos"
PADACIOSO = "ovos-padacioso-pipeline-plugin"
PIPELINE = [f"{PADACIOSO}-high", f"{PADACIOSO}-medium"]
END2END_DIR = Path(__file__).parent


def _rows():
    rows = []
    for path in sorted(END2END_DIR.glob("golden_utterances_*.jsonl")):
        lang = path.stem.removeprefix("golden_utterances_")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                assert row["lang"] == lang, f"{path.name}:{number} has lang {row['lang']!r}"
                rows.append(pytest.param(row, id=f"{lang}:{number}:{row['intent_label']}"))
    return rows


@pytest.fixture(scope="module")
def containers():
    """Boot one MiniCroft per language on first use; keep only the latest."""
    booted = {}

    def get(lang):
        if lang not in booted:
            for minicroft, _ in booted.values():
                minicroft.stop()
            booted.clear()
            minicroft = get_minicroft([SKILL_ID], lang=lang,
                                      default_pipeline=PIPELINE,
                                      wait_for_trained=False)
            container = minicroft.intents.pipeline_plugins[PADACIOSO].containers[lang]
            booted[lang] = (minicroft, container)
        return booted[lang][1]

    yield get
    for minicroft, _ in booted.values():
        minicroft.stop()


@pytest.mark.timeout(300)
@pytest.mark.parametrize("row", _rows())
def test_golden_row_matches_its_intent(containers, row):
    match = containers(row["lang"]).calc_intent(row["utterance"])
    expected = f"{SKILL_ID}:{row['intent_label']}"
    assert match.get("name") == expected, (
        f"[{row['lang']}] {row['utterance']!r}: expected {expected}, got {match.get('name')!r}"
    )


def test_every_shipping_locale_has_a_golden_file():
    golden = {p.stem.split("_", 2)[2] for p in END2END_DIR.glob("golden_utterances_*.jsonl")}
    locale_root = END2END_DIR.parents[1] / "locale"
    shipping = {d.name for d in locale_root.iterdir() if d.is_dir() and any(d.rglob("*.intent"))}
    assert golden == shipping, f"golden files {sorted(golden ^ shipping)} differ from shipping locales"
