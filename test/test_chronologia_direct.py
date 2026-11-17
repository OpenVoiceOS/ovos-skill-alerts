"""The parse functions read the skill's own phrases through chronologia and numtag.

Each row is a phrase from the skill's locale files or test rows. The clock is
frozen on Tuesday 2017-06-27 13:04 UTC, and every expected value is datetime
arithmetic on that anchor:

- A counted length runs from the anchor: "meia hora" is 30 minutes.
- A named day keeps the spoken hour: "morgen um zehn" is 10:00 on Wednesday.
- A part of the day sets the half of the day: "às oito da noite" is 20:00.
- A weekday named on that weekday with a clock already passed is the next
  one (chronologia ruling 16): "martedì alle 9" is Tuesday 4 July 09:00.
- A week is the calendar week, Monday to Sunday (ISO 8601), and "today"
  is the whole anchor day.
- An article is not a number: "dagli una priorità più bassa" names no
  priority, so the default one stays.
"""
import datetime as dt
import unittest

import time_machine
from ovos_bus_client.message import Message

from ovos_skill_alerts.util import AlertPriority
from ovos_skill_alerts.util.parse_utils import (
    parse_alert_priority_from_message,
    parse_alert_time_from_message,
    parse_end_condition_from_message,
    parse_repeat_from_message,
    parse_timeframe_from_message,
    tokenize_utterance,
)

UTC = dt.timezone.utc
ANCHOR = dt.datetime(2017, 6, 27, 13, 4, tzinfo=UTC)
LAST_SECOND = dt.timedelta(days=1, seconds=-1)


def _message(utterance: str, lang: str) -> Message:
    """A padatious-style match: the utterance and no Adapt tags."""
    return Message("intent", {"utterance": utterance, "lang": lang}, {"lang": lang})


def _alert_time(utterance: str, lang: str):
    message = _message(utterance, lang)
    with time_machine.travel(ANCHOR, tick=False):
        return parse_alert_time_from_message(message, tokenize_utterance(message), UTC, ANCHOR)


class TestAlertTime(unittest.TestCase):
    def test_half_an_hour_timer(self):
        self.assertEqual(_alert_time("põe um temporizador de meia hora", "pt-PT"),
                         ANCHOR + dt.timedelta(minutes=30))

    def test_named_day_keeps_the_hour(self):
        self.assertEqual(_alert_time("plane eine Erinnerung, dass ich morgen um zehn den Arzt anrufe", "de-DE"),
                         dt.datetime(2017, 6, 28, 10, 0, tzinfo=UTC))

    def test_part_of_the_day_sets_the_half(self):
        self.assertEqual(_alert_time("me lembre de tomar o remédio às oito da noite", "pt-BR"),
                         dt.datetime(2017, 6, 27, 20, 0, tzinfo=UTC))

    def test_same_weekday_with_a_passed_clock_is_next_week(self):
        self.assertEqual(_alert_time("segna un appuntamento dal dentista martedì alle 9", "it-IT"),
                         ANCHOR.replace(hour=9, minute=0) + dt.timedelta(weeks=1))


class TestTimeframe(unittest.TestCase):
    def _timeframe(self, utterance: str, lang: str):
        with time_machine.travel(ANCHOR, tick=False):
            return parse_timeframe_from_message(_message(utterance, lang), timezone=UTC)

    def test_this_week_is_the_calendar_week(self):
        monday = dt.datetime(2017, 6, 26, tzinfo=UTC)
        self.assertEqual(self._timeframe("zähl alle Erinnerungen auf, die diese Woche geplant sind", "de-DE"),
                         (monday, monday + dt.timedelta(days=6) + LAST_SECOND))

    def test_today_is_the_whole_day(self):
        today = dt.datetime(2017, 6, 27, tzinfo=UTC)
        self.assertEqual(self._timeframe("har jag något larm i dag", "sv-FI"),
                         (today, today + LAST_SECOND))


class TestEndAndRepeat(unittest.TestCase):
    def test_quarter_of_an_hour_end_condition(self):
        message = _message("cambia la duración de mi alarma a un cuarto de hora", "es-ES")
        with time_machine.travel(ANCHOR, tick=False):
            self.assertEqual(parse_end_condition_from_message(message), dt.timedelta(minutes=15))

    def test_every_week_repeats_after_seven_days(self):
        message = _message("o alarme deve repetir todas as semanas", "pt-PT")
        with time_machine.travel(ANCHOR, tick=False):
            self.assertEqual(parse_repeat_from_message(message), dt.timedelta(days=7))


class TestPriority(unittest.TestCase):
    def test_an_article_is_no_priority(self):
        message = _message("quell'allarme non è urgente, dagli una priorità più bassa", "it-IT")
        self.assertEqual(parse_alert_priority_from_message(message), AlertPriority.AVERAGE.value)


if __name__ == "__main__":
    unittest.main()
