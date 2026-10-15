"""Which alert handle_cancel_alert cancels when the user says "next".

With several alarms pending, "cancel my next alarm" spoke
error_nothing_to_cancel: a padacioso match carries no ``next`` flag, and the
resolver matched only by name. #431 made _resolve_requested_alert read
"next" from next.voc, and the cancel handler falls back to the resolver, so
this pins that path in several locales.
"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts import AlertSkill
from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert


def _alarm(name, hours):
    return Alert.create(
        expiration=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours),
        alert_name=name, alert_type=AlertType.ALARM)


def _cancel(utterance, alerts, lang):
    skill = SimpleNamespace(
        lang=lang, alert_manager=SimpleNamespace(),
        _get_alerts_list=lambda *a, **k: list(alerts),
        _pick_one_by_name=Mock(return_value=None),
        _dismiss_alert=Mock(), speak_dialog=Mock())
    skill._resolve_requested_alert = \
        lambda message, alert_type: AlertSkill._resolve_requested_alert(
            skill, message, alert_type)
    AlertSkill.handle_cancel_alert(skill, Message(
        "cancel_alert.intent", {"utterance": utterance, "lang": lang},
        {"lang": lang}))
    return skill


@pytest.mark.parametrize("lang, utterance", [
    ("en-US", "cancel my next alarm"),
    ("en-US", "delete the upcoming alarm"),
    ("de-DE", "lösche den nächsten Wecker"),
    ("pt-PT", "cancela o próximo alarme"),
    ("es-ES", "cancela la próxima alarma"),
])
def test_next_cancels_the_soonest_of_several(lang, utterance):
    soonest, later = _alarm("one", 3), _alarm("two", 30)
    skill = _cancel(utterance, [soonest, later], lang)
    skill._dismiss_alert.assert_called_once_with(soonest.ident, drop_dav=True)
    assert skill.speak_dialog.call_args[0][0] == "confirm_cancel_alert"
