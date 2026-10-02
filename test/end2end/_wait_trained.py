"""Shared MiniCroft-readiness helper for the end2end suite.

ovos-padatious's padaos layer drops an intent's compiled regex the
instant it is (re)registered and only rebuilds it on a background worker
thread; that worker itself waits for a quiet window with no further
registrations before it starts compiling at all (see
``ovos_padatious.intent_container._TRAIN_DEBOUNCE_S``). A query fired
before that debounce window has elapsed and the background compile has
landed is served the empty (or stale) pre-compile state and comes back
unmatched or mis-routed, regardless of how correct a skill's own
``.intent`` templates are. A fixed post-boot sleep is not a reliable fix
for this: coverage instrumentation (and any other source of runner
slowdown) stretches the wall-clock gap between "last registration" and
"skill reports READY" unevenly, so a sleep long enough on a plain run
can still land inside the debounce+compile window on a slower one -- and
that includes a fixed *grace* sleep tacked on after the first observed
completion: a second, later pass (a sibling skill/language settling
after this one) can just as easily take longer than that fixed grace
under the same slowdown, which is the same failure class relocated one
level down rather than fixed.

ovos-padatious documents ``mycroft.skills.trained`` on the bus as the
actual completion signal for this (see ``ovos_padatious.opm``'s
``PadatiousPipeline.train``/``wait_until_trained`` docstrings) -- it is
emitted once a background training pass lands, and again on every
subsequent pass. The robust wait is therefore event-driven end to end:
after READY, keep resetting a quiet-window timer on every delivery and
only return once no NEW delivery has arrived within that window (i.e.
training has genuinely gone quiet), bounded overall by ``max_trained_wait``
so a pathological stream of passes cannot block forever. A boot with
nothing to train at all (so the event never fires even once) falls back
to a short plain settle instead of blocking for the full timeout.

Both budgets raise ``MinicroftNotReady`` when they run out. An earlier
version returned instead, which made an overrun silent: the caller went
on to query a container that was still compiling, and the timeout
reached the test as a wake-routing failure or passed by luck. A caller
cannot tell a settled boot from an exhausted budget by looking at the
MiniCroft, because the skill reports READY long before padatious stops
training, so the helper must be the one that says so.
"""
import threading
import time

from ovos_utils.process_utils import ProcessState

DEFAULT_READY_TIMEOUT = 60
DEFAULT_TRAINED_TIMEOUT = 90
QUIET_WINDOW = 4.0
# Best-effort fallback only: used when `mycroft.skills.trained` never
# arrives at all (e.g. an ovos-padatious version too old to emit it) so
# callers still get *some* settle time instead of racing ahead with zero
# wait.
FALLBACK_SETTLE = 3.0


class MinicroftNotReady(AssertionError):
    """A readiness budget ran out. Raised, never returned."""


def wait_for_minicroft_ready(mc, ready_timeout: float = DEFAULT_READY_TIMEOUT,
                             max_trained_wait: float = DEFAULT_TRAINED_TIMEOUT,
                             quiet_window: float = QUIET_WINDOW) -> None:
    """Block until *mc* is READY and its padatious/padacioso containers
    have finished (re)compiling from this boot's registrations.

    :raises MinicroftNotReady: *mc* did not reach READY within
        *ready_timeout*, or training was still delivering passes when
        *max_trained_wait* ran out.
    """
    trained = threading.Event()

    def _on_trained(_msg):
        trained.set()

    mc.bus.on("mycroft.skills.trained", _on_trained)
    try:
        deadline = time.monotonic() + ready_timeout
        while getattr(getattr(mc, "status", None), "state", None) != ProcessState.READY:
            if time.monotonic() > deadline:
                raise MinicroftNotReady(
                    f"MiniCroft did not reach READY within {ready_timeout}s; "
                    f"state="
                    f"{getattr(getattr(mc, 'status', None), 'state', None)!r}"
                )
            time.sleep(0.2)

        overall_deadline = time.monotonic() + max_trained_wait
        saw_any = False
        settled = False
        while True:
            remaining = overall_deadline - time.monotonic()
            if remaining <= 0:
                break  # budget gone with training still arriving
            window = min(quiet_window, remaining)
            if trained.wait(timeout=window):
                trained.clear()
                saw_any = True
                continue  # a delivery landed -- reset the quiet-window clock
            if window < quiet_window:
                break  # the budget cut the window short: it proves nothing
            settled = True
            break  # quiet_window elapsed with no new delivery: settled

        if not settled:
            raise MinicroftNotReady(
                f"padatious was still training when the {max_trained_wait}s "
                f"budget ran out: no quiet window of {quiet_window}s ever "
                f"closed. Queries now would read a half-compiled container. "
                f"Raise max_trained_wait or lighten the boot."
            )

        if not saw_any:
            time.sleep(FALLBACK_SETTLE)
    finally:
        mc.bus.remove("mycroft.skills.trained", _on_trained)
