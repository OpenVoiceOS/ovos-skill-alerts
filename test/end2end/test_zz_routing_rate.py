"""The share of end2end requests that reached their intent on m2v.

Pytest runs this module after the other end2end modules, which record each
routed request in ``_routing``. A request that reached another intent skipped
its own test; this test fails the run when too many did.
"""
import pytest

from ._routing import HITS, MISSES

# m2v routes 83% to 86% of the suite's requests as expected on the published
# model, and the share moves by a few points from one boot to the next.
MIN_ROUTING_RATE = 0.75


def test_enough_requests_reach_their_intent():
    total = len(HITS) + len(MISSES)
    if not total:
        pytest.skip("no end2end module recorded a routed request in this run")
    rate = len(HITS) / total
    print(f"{rate:.1%} of {total} requests reached their intent; misses:",
          *MISSES, sep="\n  ")
    assert rate >= MIN_ROUTING_RATE, (
        f"{rate:.1%} of {total} requests reached their intent, below "
        f"{MIN_ROUTING_RATE:.0%}:\n  " + "\n  ".join(MISSES))
