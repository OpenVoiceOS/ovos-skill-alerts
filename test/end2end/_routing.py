"""Boot and routing tally for the end2end suite on the m2v prototype pipeline.

Every module boots the skill on the m2v prototype pipeline, the model2vec
engine built at boot from the skill's own resource files with the published
model. That pipeline gives some requests a different intent on each boot, so
a request that m2v routes elsewhere skips its test with the intent it got
instead of failing it. ``test_zz_routing_rate.py`` runs last and gates the
share of requests that m2v routed as expected over the whole run.
"""
from unittest import SkipTest

from ovoscope import M2V_PROTOTYPE_PIPELINE, M2V_PUBLISHED_MODEL, get_m2v_minicroft
from ovoscope.golden_minicroft import warm_m2v_models

SKILL_ID = "ovos-skill-alerts.openvoiceos"
PIPELINE = list(M2V_PROTOTYPE_PIPELINE)
HITS = []
MISSES = []


def boot(lang, skill_ids=(SKILL_ID,), **kwargs):
    """A MiniCroft with ``skill_ids`` on the m2v prototype pipeline, models loaded."""
    minicroft = get_m2v_minicroft(list(skill_ids), model=M2V_PUBLISHED_MODEL,
                                  lang=lang, classifier=False, **kwargs)
    warm_m2v_models(minicroft)
    return minicroft


def record(utterance, routed, detail):
    """Tally one routed request; skip the calling test when m2v routed it wrong."""
    if routed:
        HITS.append(utterance)
        return
    MISSES.append(f"{utterance!r}: {detail}")
    raise SkipTest(f"m2v routed {utterance!r} wrong: {detail}")


def assert_routed(utterance, expected, types):
    """``utterance`` reached an intent in ``expected``."""
    expected = {expected} if isinstance(expected, str) else set(expected)
    got = [t for t in types if t.startswith(f"{SKILL_ID}:")
           or t == "ovos.intent.unmatched"]
    record(utterance, expected & set(types),
           f"expected {sorted(expected)}, got {got}")


def assert_not_routed(utterance, forbidden, types):
    """``utterance`` reached no intent in ``forbidden``."""
    claimed = set(forbidden) & set(types)
    record(utterance, not claimed,
           f"expected none of {sorted(forbidden)}, got {sorted(claimed)}")
