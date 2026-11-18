"""The ru-RU word for an alarm clock is "будильник".

dialog/words/alarm.dialog held "сигнализация", a security alarm system, so
"Ваш {kind} установлен..." confirmed an alarm clock as a burglar alarm, and in
the wrong gender for the masculine "Ваш ... установлен".
"""
from ovos_workshop.resource_files import SkillResources

from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.locale import spoken_alert_type

import os

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_ru_alarm_kind_is_an_alarm_clock():
    assert spoken_alert_type(AlertType.ALARM, "ru-RU") == "будильник"


def test_the_ru_alarm_confirmation_names_an_alarm_clock():
    text = SkillResources(SKILL_ROOT, "ru-ru").render_dialog(
        "confirm_alert_set",
        {"kind": spoken_alert_type(AlertType.ALARM, "ru-RU"),
         "begin": "7:00", "remaining": "8 часов"})
    assert "будильник" in text and "сигнализац" not in text
