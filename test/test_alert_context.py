import datetime as dt
import unittest
from time import time

from ovos_bus_client.message import Message

from util.parse_utils import parse_alert_context_from_message


class TestAlertContext(unittest.TestCase):
    def test_created_is_request_time(self):
        """A stale timestamp in message context must not anchor the alert."""
        stale = dt.datetime(2022, 2, 12).timestamp()
        message = Message("test", {},
                          {"timing": {"handle_utterance": stale}})

        created = parse_alert_context_from_message(message)["created"]

        self.assertAlmostEqual(created, time(), delta=5)


if __name__ == "__main__":
    unittest.main()
