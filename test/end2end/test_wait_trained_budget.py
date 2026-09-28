"""The readiness helper's budgets are loud.

`wait_for_minicroft_ready` used to return when a budget ran out. A caller
then queried a container that was still compiling, and the timeout reached
the tests as a wake-routing failure, or passed by luck. The fixture in
test_wake_arbitration.py tried to cover this with an assert on READY, which
cannot see it: a skill reports READY long before padatious stops training,
so the assert passes on exactly the boot it was written to catch.

These cases drive the helper with a stub MiniCroft instead of a real boot,
so they run in seconds and do not need the model set. The still-training
stub is the negative; the settling stub is its control, and it must pass in
the same run or the negative proves only that the helper raises always.
"""
import threading
import time
import unittest

from ovos_utils.process_utils import ProcessState

from ._wait_trained import MinicroftNotReady, wait_for_minicroft_ready


class _Status:
    def __init__(self, state):
        self.state = state


class _Bus:
    """Calls every `mycroft.skills.trained` handler on a timer."""

    def __init__(self, period=None, passes=0):
        self._handlers = {}
        self._stop = threading.Event()
        self._thread = None
        self._period = period
        self._passes = passes

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def remove(self, event, handler):
        self._handlers.get(event, []).remove(handler)

    def start(self):
        if self._period is None:
            return
        self._thread = threading.Thread(target=self._emit, daemon=True)
        self._thread.start()

    def _emit(self):
        sent = 0
        while not self._stop.wait(self._period):
            if self._passes and sent >= self._passes:
                return
            sent += 1
            for handler in list(self._handlers.get(
                    "mycroft.skills.trained", [])):
                handler(None)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


class _MiniCroft:
    def __init__(self, bus, state=ProcessState.READY):
        self.bus = bus
        self.status = _Status(state)


class TestTrainedBudgetIsLoud(unittest.TestCase):

    def _run(self, bus, **kwargs):
        mc = _MiniCroft(bus)
        bus.start()
        try:
            wait_for_minicroft_ready(mc, **kwargs)
        finally:
            bus.stop()

    def test_a_train_that_never_settles_raises(self):
        """Passes keep arriving inside the quiet window until the budget
        is gone. The old helper returned here and said nothing."""
        bus = _Bus(period=0.05)
        started = time.monotonic()
        with self.assertRaises(MinicroftNotReady) as caught:
            self._run(bus, ready_timeout=2, max_trained_wait=1.0,
                      quiet_window=0.4)
        self.assertIn("still training", str(caught.exception))
        self.assertLess(time.monotonic() - started, 5)

    def test_a_train_that_settles_returns(self):
        """The control: two passes, then quiet. Same helper, no raise."""
        bus = _Bus(period=0.05, passes=2)
        self._run(bus, ready_timeout=2, max_trained_wait=5.0,
                  quiet_window=0.4)

    def test_a_boot_with_nothing_to_train_returns(self):
        """No pass ever arrives: the fallback settle, still no raise."""
        bus = _Bus()
        self._run(bus, ready_timeout=2, max_trained_wait=5.0,
                  quiet_window=0.4)

    def test_a_boot_that_never_reaches_ready_raises(self):
        mc = _MiniCroft(_Bus(), state=ProcessState.STARTED)
        with self.assertRaises(MinicroftNotReady) as caught:
            wait_for_minicroft_ready(mc, ready_timeout=0.5,
                                     max_trained_wait=1.0, quiet_window=0.4)
        self.assertIn("READY", str(caught.exception))

    def test_a_budget_shorter_than_the_quiet_window_is_not_settled(self):
        """A window the budget cut short proves no quiet window closed."""
        bus = _Bus()
        with self.assertRaises(MinicroftNotReady):
            self._run(bus, ready_timeout=2, max_trained_wait=0.2,
                      quiet_window=4.0)


if __name__ == "__main__":
    unittest.main()
