"""A comma after the time must not change the time an alert request reads.

"despiértame a las 8, por favor" names 08:00. With the comma glued to the
hour, older date parsers read no time. The gold is the hour the words name.
"""
import datetime as dt

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts.util.parse_utils import parse_alert_time_from_message


@pytest.mark.parametrize("lang, utterance", [
    ("es-ES", "despiértame a las 8, por favor"),
    ("gl-ES", "espértame ás 8, por favor"),
])
def test_a_comma_after_the_hour_keeps_the_hour(lang, utterance):
    message = Message("create_alarm.intent",
                      {"utterance": utterance, "lang": lang}, {"lang": lang})
    anchor = dt.datetime(2026, 1, 15, 6, 0)
    result = parse_alert_time_from_message(message, anchor_time=anchor)
    assert result == dt.datetime(2026, 1, 15, 8, 0)
