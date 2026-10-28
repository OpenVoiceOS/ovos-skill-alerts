"""
A counted duration of hours or minutes is elapsed time. It must not shift
when the interval crosses a DST change in the configured zone.
"""
import datetime as dt
import unittest
from os.path import dirname, join
from unittest.mock import patch
from zoneinfo import ZoneInfo

import time_machine
from ovos_bus_client.message import Message

LISBON = ZoneInfo("Europe/Lisbon")
UTC = dt.timezone.utc
EXAMPLES = join(dirname(__file__), "example_messages")


def _message(filename: str, utterance: str) -> Message:
    with open(join(EXAMPLES, filename)) as f:
        msg = Message.deserialize(f.read())
    msg.data["utterance"] = utterance
    msg.data["utterances"] = [utterance]
    return msg


def _utc(*args) -> dt.datetime:
    return dt.datetime(*args, tzinfo=UTC)


class TestElapsedDurations(unittest.TestCase):
    def _expiration(self, filename, utterance, now_utc):
        from ovos_skill_alerts.util import parse_utils
        with time_machine.travel(now_utc, tick=False), \
                patch.object(parse_utils, "get_default_tz", return_value=LISBON):
            alert_time = parse_utils.parse_alert_time_from_message(
                _message(filename, utterance))
        self.assertEqual(alert_time.tzinfo, LISBON)
        return alert_time

    # Gold values: the anchor in UTC plus the counted seconds, by hand.
    def test_eight_hours_across_autumn_change(self):
        # 18:16 WEST is 17:16 UTC; the clocks go back at 01:00 UTC on 2026-10-25.
        # 8 h later is 01:16 UTC = 01:16 WET (UTC+0).
        now = _utc(2026, 10, 24, 17, 16)
        alert_time = self._expiration("wake_me_up_in_time_alarm.json",
                                      "wake me up in 8 hours", now)
        self.assertEqual((alert_time - now).total_seconds(), 8 * 3600)
        self.assertEqual(alert_time.astimezone(UTC), _utc(2026, 10, 25, 1, 16))
        self.assertEqual(alert_time.hour, 1)

    def test_eight_hours_across_spring_change(self):
        # The clocks go forward at 01:00 UTC on 2027-03-28.
        # 17:30 UTC + 8 h = 01:30 UTC = 02:30 WEST.
        now = _utc(2027, 3, 27, 17, 30)
        alert_time = self._expiration("wake_me_up_in_time_alarm.json",
                                      "wake me up in 8 hours", now)
        self.assertEqual(alert_time.astimezone(UTC), _utc(2027, 3, 28, 1, 30))
        self.assertEqual((alert_time.hour, alert_time.minute), (2, 30))

    def test_ninety_minute_timer_on_the_change_night(self):
        # 00:50 WEST is 23:50 UTC on 10-24. 90 min later is 01:20 UTC = 01:20 WET.
        now = _utc(2026, 10, 24, 23, 50)
        alert_time = self._expiration("set_time_timer.json",
                                      "set a timer for 90 minutes", now)
        self.assertEqual((alert_time - now).total_seconds(), 90 * 60)
        self.assertEqual(alert_time.astimezone(UTC), _utc(2026, 10, 25, 1, 20))
        self.assertEqual((alert_time.hour, alert_time.minute), (1, 20))

    def test_no_change_in_the_interval(self):
        # Control: 2026-10-20 12:00 UTC + 8 h, no transition in between.
        now = _utc(2026, 10, 20, 12, 0)
        alert_time = self._expiration("wake_me_up_in_time_alarm.json",
                                      "wake me up in 8 hours", now)
        self.assertEqual(alert_time.astimezone(UTC), _utc(2026, 10, 20, 20, 0))
        self.assertEqual(alert_time.hour, 21)

    def test_timedelta_across_the_change(self):
        # Snooze "for 8 hours" at 17:16 UTC on 10-24 is 8 real hours.
        from ovos_skill_alerts.util import parse_utils
        now = _utc(2026, 10, 24, 17, 16)
        with time_machine.travel(now, tick=False), \
                patch.object(parse_utils, "get_default_tz", return_value=LISBON):
            delta = parse_utils.parse_timedelta_from_message(
                _message("snooze_for_duration_converse.json", "snooze for 8 hours"),
                anchor_time=now.astimezone(LISBON))
        self.assertEqual(delta, dt.timedelta(hours=8))

    def test_alert_built_from_intent_across_the_change(self):
        from ovos_skill_alerts.util import parse_utils
        now = _utc(2026, 10, 24, 17, 16)
        msg = _message("wake_me_up_in_time_alarm.json", "wake me up in 8 hours")
        msg.context["created"] = now.timestamp()
        with time_machine.travel(now, tick=False), \
                patch.object(parse_utils, "get_default_tz", return_value=LISBON), \
                patch.object(parse_utils, "get_session_tz", return_value=LISBON):
            alert = parse_utils.build_alert_from_intent(msg)
            self.assertEqual(alert.time_to_expiration, dt.timedelta(hours=8))

    def test_stored_expiration_in_the_repeated_hour_keeps_its_instant(self):
        # 01:20 WET on 2026-10-25 is the second 01:20 of that night: 01:20 UTC.
        from ovos_skill_alerts.util import AlertType
        from ovos_skill_alerts.util.alert import Alert
        second_pass = _utc(2026, 10, 25, 1, 20).astimezone(LISBON)
        self.assertEqual(second_pass.utcoffset(), dt.timedelta(0))
        # An expired alert reports no expiration, so the clock stays before it.
        with time_machine.travel(_utc(2026, 10, 24, 23, 50), tick=False):
            alert = Alert.create(expiration=second_pass, alert_name="timer",
                                 alert_type=AlertType.TIMER, lang="en-US")
            self.assertEqual(alert.expiration.astimezone(UTC),
                             _utc(2026, 10, 25, 1, 20))

    def test_timer_set_in_the_repeated_hour_survives_storage(self):
        # 90 min after 23:50 UTC is 01:20 UTC, which is 01:20 WET.
        from ovos_skill_alerts.util import AlertType, parse_utils
        from ovos_skill_alerts.util.alert import Alert
        now = _utc(2026, 10, 24, 23, 50)
        expiration = self._expiration("set_time_timer.json",
                                      "set a timer for 90 minutes", now)
        with time_machine.travel(now, tick=False):
            alert = Alert.create(expiration=expiration, alert_name="timer",
                                 alert_type=AlertType.TIMER, lang="en-US")
            self.assertEqual(alert.expiration.astimezone(UTC) - now,
                             dt.timedelta(minutes=90))

    def test_spoken_duration_counts_elapsed_time(self):
        # 23:50 UTC to 01:20 UTC is 90 minutes; the Lisbon wall clock moves 30.
        from ovos_skill_alerts.util.locale import spoken_duration
        now = _utc(2026, 10, 24, 23, 50).astimezone(LISBON)
        later = _utc(2026, 10, 25, 1, 20).astimezone(LISBON)
        self.assertEqual(spoken_duration(later, now, "en-US"),
                         spoken_duration(dt.timedelta(minutes=90), lang="en-US"))
        self.assertNotEqual(spoken_duration(later, now, "en-US"),
                            spoken_duration(dt.timedelta(minutes=30), lang="en-US"))


if __name__ == "__main__":
    unittest.main()
