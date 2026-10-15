"""Which alert _resolve_requested_alert picks when the user says "next".

Adapt tagged "next" as a ``next`` flag, but a padacioso match carries only
the utterance. With several alerts of a kind pending, "reschedule the next
event two hours earlier" resolved to none of them and the skill spoke
error_no_scheduled_kind. "next" is read from the words left once the time is
parsed out, so "the baseball event to next monday" still picks by name.
"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert


def _alert(name, alert_type, hours):
    return Alert.create(
        expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours),
        alert_name=name, alert_type=alert_type)


def _pick(alerts, dialog=""):
    """One candidate is taken; several would be asked about."""
    return alerts[0] if len(alerts) == 1 else "ASKED" if alerts else None


def _resolve(utterance, alert_type, alerts, lang="en-US"):
    skill = SimpleNamespace(lang=lang,
                            _get_alerts_list=lambda *a, **k: list(alerts),
                            _pick_one_by_name=Mock(side_effect=_pick))
    return AlertSkill._resolve_requested_alert(skill, Message(
        "reschedule_alert.intent", {"utterance": utterance, "lang": lang},
        {"lang": lang}), alert_type)


@pytest.mark.parametrize("utterance, alert_type", [
    ("reschedule the next event two hours earlier", AlertType.EVENT),
    ("move the next event to 8 pm", AlertType.EVENT),
    ("postpone my next alarm by 10 minutes", AlertType.ALARM),
])
def test_next_picks_the_soonest_of_several(utterance, alert_type):
    soonest = _alert("meeting", alert_type, 3)
    later = _alert("baseball", alert_type, 30)
    assert _resolve(utterance, alert_type, [soonest, later]) is soonest


def test_next_as_part_of_the_time_does_not_pick_the_soonest():
    soonest = _alert("meeting", AlertType.EVENT, 3)
    baseball = _alert("baseball", AlertType.EVENT, 30)
    assert _resolve("move the baseball event to next monday",
                    AlertType.EVENT, [soonest, baseball]) is not soonest


def test_an_unknown_name_with_next_in_the_time_resolves_to_none():
    alerts = [_alert("meeting", AlertType.EVENT, 3),
              _alert("baseball", AlertType.EVENT, 30)]
    assert _resolve("move the zoo event to next monday",
                    AlertType.EVENT, alerts) is None


@pytest.mark.parametrize("lang, utterance, alert_type", [
    ("en-US", "move the upcoming event to 8 pm", AlertType.EVENT),
    ("de-DE", "verschiebe den nächsten Termin auf 20 Uhr", AlertType.EVENT),
    ("de-DE", "verschiebe den nächsten Wecker um 10 Minuten", AlertType.ALARM),
    ("it-IT", "rimanda la prossima sveglia di 10 minuti", AlertType.ALARM),
    ("fr-FR", "décale mon prochain réveil de 10 minutes", AlertType.ALARM),
    ("es-ES", "mueve la próxima alarma 10 minutos", AlertType.ALARM),
    ("pt-BR", "mova o próximo alarme para as seis", AlertType.ALARM),
    ("pt-BR", "mude a próxima consulta para as seis", AlertType.EVENT),
    ("pt-PT", "muda o próximo alarme para as seis", AlertType.ALARM),
    ("nl-NL", "verzet de eerstvolgende wekker naar acht uur", AlertType.ALARM),
    ("sv-SE", "flytta det kommande larmet till klockan åtta", AlertType.ALARM),
    ("ru-RU", "перенеси следующее событие на восемь вечера", AlertType.EVENT),
])
def test_each_locale_reads_its_own_next_word(lang, utterance, alert_type):
    soonest = _alert("eins", alert_type, 3)
    later = _alert("zwei", alert_type, 30)
    assert _resolve(utterance, alert_type, [soonest, later], lang) is soonest


@pytest.mark.parametrize("utterance", [
    "move the next steps reminder to 5 pm",
    "move the reminder for next steps to 5 pm",
])
def test_an_alert_named_with_the_next_word_is_taken_by_its_name(utterance):
    dentist = _alert("dentist", AlertType.REMINDER, 3)
    next_steps = _alert("next steps", AlertType.REMINDER, 30)
    assert _resolve(utterance, AlertType.REMINDER,
                    [dentist, next_steps]) is next_steps
