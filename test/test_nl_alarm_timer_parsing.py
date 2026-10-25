"""Dutch (nl-NL) time parsing for alarms and timers.

Dutch "7 uur" is both "7 o'clock" and "7 hours", and "voor"/"op" before a
clock time and "een kwartier" are not read by ovos-date-parser, so parse_utils
rewrites them for Dutch alarms and timers. A bare "7 uur" means the next 7:00,
so it may land on 07:00 or 19:00 depending on the time of day; the tests accept
both.
"""
import datetime as dt
import re
from importlib.metadata import version

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts.util.parse_utils import build_alert_from_intent


def _date_parser_version():
    return tuple(int(p) for p in re.findall(r"\d+", version("ovos-date-parser"))[:2])


# "half 8", "kwart over" and "om 7 uur" are read correctly from 0.35 on
needs_current_date_parser = pytest.mark.skipif(
    _date_parser_version() < (0, 35),
    reason="ovos-date-parser < 0.35 misreads Dutch clock times")


def _alert(utterance):
    message = Message("intent", {"utterance": utterance, "lang": "nl-NL"},
                      {"lang": "nl-NL"})
    return build_alert_from_intent(message)


# (utterance, hour, minute): the hour is read modulo 12, since a bare "7 uur"
# is the next 7:00, which is 07:00 or 19:00
CLOCK_CASES = [
    ("zet een wekker om 7 uur", 7, 0),
    ("zet een wekker voor 7 uur", 7, 0),
    ("zet een wekker op 7 uur", 7, 0),
    ("stel een wekker in voor 7 uur", 7, 0),
    ("zet een alarm voor 6 uur", 6, 0),
    ("kun je een wekker zetten voor 8 uur", 8, 0),
    ("zet een wekker voor morgen om 7 uur", 7, 0),
    ("ik wil een wekker voor morgenochtend 7 uur", 7, 0),
    ("wek me om 7 uur", 7, 0),
    ("maak me om 6 uur wakker", 6, 0),
    ("zet de wekker op half 8", 7, 30),
    ("wek me morgen om half 7", 6, 30),
    ("zet de wekker op kwart over zeven", 7, 15),
    ("zet een wekker voor kwart voor acht", 7, 45),
]


@needs_current_date_parser
@pytest.mark.parametrize("utterance,hour,minute", CLOCK_CASES)
def test_alarm_is_set_for_the_clock_time(utterance, hour, minute):
    alert = _alert(utterance)
    assert alert.expiration is not None, f"no time for {utterance!r}"
    assert (alert.expiration.hour % 12, alert.expiration.minute) == (hour % 12, minute), (
        f"{utterance!r} became {alert.expiration:%a %H:%M}")


DURATION_CASES = [
    ("zet een timer voor 5 minuten", 5),
    ("zet een timer van tien minuten", 10),
    ("stel een timer in voor 20 minuten", 20),
    ("zet een eierwekker op 8 minuten", 8),
    ("zet een timer voor een kwartier", 15),
    ("zet een timer voor drie kwartier", 45),
    ("start een eierwekker van een kwartier", 15),
    ("zet een timer voor een half uur", 30),
    ("zet een timer voor 1 uur en 20 minuten", 80),
    ("wek me over een half uur", 30),
    ("wek me over twee uur", 120),
    ("zet een wekker over een kwartier", 15),
    ("zet een wekker over 45 minuten", 45),
]


@pytest.mark.parametrize("utterance,minutes", DURATION_CASES)
def test_duration_is_read_as_minutes_from_now(utterance, minutes):
    alert = _alert(utterance)
    assert alert.expiration is not None, f"no time for {utterance!r}"
    delta = (alert.expiration - dt.datetime.now(alert.expiration.tzinfo)).total_seconds() / 60
    assert abs(delta - minutes) < 1.5, f"{utterance!r} is {delta:.1f} min from now"
