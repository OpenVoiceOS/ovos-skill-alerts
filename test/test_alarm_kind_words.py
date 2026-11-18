"""An alarm-clock request is classified as an alarm in each locale.

get_alert_type_from_intent reads the kind from alarm.voc when the intent
carries no Adapt tag. ru-RU alarm.voc held only разбуди меня, сигнализации
and сигнализация, so "отмени мой будильник" was not an alarm request; other
locales lacked the everyday alarm-clock word their intents use, such as it-IT
sveglia, pl-PL budzik and cs-CZ budík.
"""
import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.locale import get_alert_type_from_intent


@pytest.mark.parametrize("lang, utterance", [
    ("ru-RU", "отмени мой будильник"),
    ("ru-RU", "поставь будильник на семь"),
    ("ru-RU", "сколько времени до будильника"),
    ("ru-RU", "выключи сигнализацию"),
    ("it-IT", "cancella la sveglia"),
    ("pl-PL", "usuń budzik"),
    ("cs-CZ", "zruš budík"),
    ("hu-HU", "töröld az ébresztőt"),
    ("es-ES", "cancela el despertador"),
    ("pt-PT", "cancela o despertador"),
    ("ca-ES", "cancel·la el despertador"),
    ("gl-ES", "cancela o espertador"),
    ("fr-FR", "annule mon réveil"),
    ("da-DK", "slet mit vækkeur"),
    ("fi-FI", "poista herätyskello"),
    ("nl-NL", "verwijder mijn alarm"),
    ("sv-SE", "ta bort väckarklockan"),
])
def test_an_alarm_clock_request_is_an_alarm(lang, utterance):
    message = Message("cancel_alert.intent",
                      {"utterance": utterance, "lang": lang}, {"lang": lang})
    assert get_alert_type_from_intent(message)[0] == AlertType.ALARM
