"""The new time a reschedule request asks for, as reschedule_alert.intent fills it.

A padacioso or padatious match carries no Adapt ``__tags__`` and no
``earlier`` flag, only the utterance. The parser must still read the
direction from the words, and a time of day must land on the alert's own
day, not on today.
"""
import datetime as dt

import pytest
from ovos_bus_client.message import Message
from ovos_config.locale import get_default_tz

from ovos_skill_alerts.util.parse_utils import parse_relative_time_from_message


def _message(utterance, lang="en-US"):
    return Message("reschedule_alert.intent",
                   {"utterance": utterance, "lang": lang},
                   {"lang": lang})


def _days_ahead(days, hour):
    now = dt.datetime.now(get_default_tz())
    return (now + dt.timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0)


@pytest.mark.parametrize("utterance, delta", [
    ("decrease the bread timer by 5 minutes", dt.timedelta(minutes=-5)),
    ("reschedule the next event two hours earlier", dt.timedelta(hours=-2)),
    ("trim five minutes off my timer", dt.timedelta(minutes=-5)),
    ("extend the pizza timer by 2 minutes", dt.timedelta(minutes=2)),
])
def test_a_duration_keeps_the_direction_the_words_ask_for(utterance, delta):
    assert parse_relative_time_from_message(
        _message(utterance), anchor_time=_days_ahead(1, 18)) == delta


@pytest.mark.parametrize("lang, utterance", [
    ("pt-BR", "adiantar o alarme em 10 minutos"),
    ("fa-IR", "زنگ را ۱۰ دقیقه زودتر کن"),
])
def test_the_locales_that_had_no_earlier_words_read_earlier(lang, utterance):
    result = parse_relative_time_from_message(_message(utterance, lang))
    assert result == dt.timedelta(minutes=-10)


def test_a_time_of_day_lands_on_the_alerts_own_day():
    anchor = _days_ahead(1, 18)
    result = parse_relative_time_from_message(
        _message("move the baseball event to 08:00 pm"), anchor_time=anchor)
    assert result == anchor.replace(hour=20)


def test_a_named_day_is_read_from_now_not_from_the_alert():
    result = parse_relative_time_from_message(
        _message("move the baseball event to tomorrow at 8 pm"),
        anchor_time=_days_ahead(3, 18))
    assert result == _days_ahead(1, 20)


def _skip_late_in_the_day(hour):
    if dt.datetime.now(get_default_tz()).hour >= hour:
        pytest.skip("the named time of today has already gone by")


@pytest.mark.parametrize("lang, utterance", [
    ("en-US", "move the dinner event to tonight at 11:30 pm"),
    ("en-US", "move the dinner event to today at 11:30 pm"),
    ("de-DE", "verschiebe den Termin auf heute um 23:30 Uhr"),
    ("pt-BR", "mude o evento para hoje às 23:30"),
])
def test_a_time_that_names_today_is_read_from_now(lang, utterance):
    _skip_late_in_the_day(23)
    result = parse_relative_time_from_message(
        _message(utterance, lang), anchor_time=_days_ahead(4, 18))
    assert result == _days_ahead(0, 23).replace(minute=30)


@pytest.mark.parametrize("lang, utterance, delta", [
    ("de-DE", "verkürze den Timer um 5 Minuten", dt.timedelta(minutes=-5)),
    ("pt-BR", "antecipar o alarme em 10 minutos", dt.timedelta(minutes=-10)),
    ("pt-BR", "passe o alarme mais para adiante 10 minutos",
     dt.timedelta(minutes=10)),
    ("it-IT", "anticipa la sveglia di 10 minuti", dt.timedelta(minutes=-10)),
    ("it-IT", "posticipa la prima sveglia di 10 minuti",
     dt.timedelta(minutes=10)),
])
def test_each_locale_reads_the_direction_its_words_ask_for(lang, utterance,
                                                           delta):
    result = parse_relative_time_from_message(
        _message(utterance, lang), anchor_time=_days_ahead(1, 7))
    assert result == delta
