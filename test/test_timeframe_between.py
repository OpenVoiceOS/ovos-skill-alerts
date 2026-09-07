import datetime as dt
import unittest
from unittest.mock import patch

from ovos_bus_client.message import Message

from ovos_skill_alerts.util.parse_utils import parse_timeframe_from_message

ANCHOR = dt.datetime(2024, 2, 2, 8, 0, 0, tzinfo=dt.timezone.utc)


def _padatious_message(utterance: str) -> Message:
    """
    Build a message the way a padatious/padacioso template intent match
    looks: no "__tags__", "and", or other adapt-populated keys, just the
    raw utterance. This is the shape ListAlerts3.intent produces.
    """
    return Message("intent", {"utterance": utterance, "lang": "en-us"}, {})


class TestTimeframeBetween(unittest.TestCase):
    def test_between_two_clock_times(self):
        message = _padatious_message(
            "are there any alerts between 4 pm and 5 pm")
        with patch("ovos_skill_alerts.util.parse_utils.dt.datetime") as mock_dt:
            mock_dt.now.return_value = ANCHOR
            mock_dt.timedelta = dt.timedelta
            begin, end = parse_timeframe_from_message(message, timezone=dt.timezone.utc)
        self.assertEqual(begin, dt.datetime(2024, 2, 2, 16, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(end, dt.datetime(2024, 2, 2, 17, 0, tzinfo=dt.timezone.utc))

    def test_between_two_clock_times_alt_phrasing(self):
        message = _padatious_message(
            "do i have anything between 9 am and 11 am")
        with patch("ovos_skill_alerts.util.parse_utils.dt.datetime") as mock_dt:
            mock_dt.now.return_value = ANCHOR
            mock_dt.timedelta = dt.timedelta
            begin, end = parse_timeframe_from_message(message, timezone=dt.timezone.utc)
        self.assertEqual(begin, dt.datetime(2024, 2, 2, 9, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(end, dt.datetime(2024, 2, 2, 11, 0, tzinfo=dt.timezone.utc))


if __name__ == "__main__":
    unittest.main()
