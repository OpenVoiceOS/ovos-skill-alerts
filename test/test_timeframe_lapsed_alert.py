"""A lapsed pending alert must not break a timeframe query.

`Alert.expiration` returns None once an alert has gone past with no repeat
left, and `AlertManager.get_alerts_in_timeframe` passes that property straight
into `alert_time_in_range`. Before the guard, one such alert in the pending
store raised TypeError, `handle_event_timeframe_check` died, and the skill
spoke `skill.error` at the user.

Every test here carries its own positive control, so a guard that answers
False to everything cannot pass this file.
"""
import datetime as dt
import unittest

from ovos_config.locale import get_default_tz

from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert, alert_time_in_range
from ovos_skill_alerts.util.alert_manager import AlertManager


def _tz():
    return get_default_tz()


def _event(name, expiration, until):
    return Alert.create(expiration=expiration, until=until, alert_name=name,
                        alert_type=AlertType.EVENT)


class TestAlertTimeInRange(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.now(_tz())

    def test_a_none_reference_start_overlaps_nothing(self):
        """The defect: a lapsed alert's expiration is None."""
        lapsed = _event("lapsed", self.now - dt.timedelta(minutes=5),
                        self.now + dt.timedelta(minutes=25))
        self.assertIsNone(lapsed.expiration,
                          "fixture is wrong: this alert has not lapsed")
        self.assertFalse(
            alert_time_in_range(self.now, None, lapsed.expiration, lapsed.until))
        self.assertFalse(
            alert_time_in_range(self.now, self.now + dt.timedelta(hours=1),
                                lapsed.expiration, lapsed.until))

    def test_a_live_alert_in_the_window_still_overlaps(self):
        """The control: the same call answers True for an alert that is live."""
        start = self.now + dt.timedelta(hours=2)
        live = _event("live", start, start + dt.timedelta(hours=1))
        self.assertIsNotNone(live.expiration)
        self.assertTrue(
            alert_time_in_range(start + dt.timedelta(minutes=10), None,
                                live.expiration, live.until))
        self.assertTrue(
            alert_time_in_range(start - dt.timedelta(minutes=10),
                                start + dt.timedelta(minutes=10),
                                live.expiration, live.until))

    def test_a_live_alert_outside_the_window_does_not_overlap(self):
        start = self.now + dt.timedelta(hours=8)
        live = _event("far", start, start + dt.timedelta(hours=1))
        self.assertFalse(
            alert_time_in_range(self.now, self.now + dt.timedelta(hours=1),
                                live.expiration, live.until))


class TestTimeframeQueryWithALapsedAlert(unittest.TestCase):
    """The user-facing path: AlertManager.get_alerts_in_timeframe."""

    def setUp(self):
        self.now = dt.datetime.now(_tz())
        self.manager = AlertManager.__new__(AlertManager)
        self.manager._pending_alerts = {}
        import threading
        self.manager._read_lock = threading.Lock()

    def _add(self, alert):
        self.manager._pending_alerts[alert.alert_name] = alert

    def test_a_lapsed_alert_does_not_break_the_query(self):
        lapsed = _event("lapsed", self.now - dt.timedelta(minutes=5),
                        self.now + dt.timedelta(minutes=25))
        self.assertIsNone(lapsed.expiration)
        self._add(lapsed)

        window_start = self.now + dt.timedelta(hours=2)
        inside = _event("inside", window_start,
                        window_start + dt.timedelta(minutes=30))
        self._add(inside)

        found = self.manager.get_alerts_in_timeframe(
            window_start - dt.timedelta(minutes=5),
            window_start + dt.timedelta(minutes=5),
            alert_type=AlertType.EVENT)
        names = [alert.alert_name for alert in found]
        # The control is in the same call: the live alert is still found, so
        # the query really ran rather than being swallowed.
        self.assertEqual(names, ["inside"])


if __name__ == "__main__":
    unittest.main()
