"""Gate (e): RescheduleAlertAlt is registered against its own padatious
file (RescheduleAlertAlt.intent) as a DISTINCT intent label from
RescheduleAlert/RescheduleAlert2, so a phrase can legitimately be matched
under either label (see test/end2end/_gate_probe.py's
EQUIVALENT_LABELS note). That is only safe because the two handlers are
behaviorally identical: handle_reschedule_alert_alt is a pure delegate to
handle_reschedule_alert. This test pins that delegation at the handler
level, independent of any pipeline/matching behavior.
"""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ovos_bus_client.message import Message
from ovos_skill_alerts import AlertSkill


class TestRescheduleAlertAltDelegation(TestCase):
    def test_reschedule_alert_alt_delegates_to_reschedule_alert(self):
        message = Message("intent", {"change": "change", "timer": "timer"})
        skill = MagicMock(spec=AlertSkill)

        result = AlertSkill.handle_reschedule_alert_alt(skill, message)

        skill.handle_reschedule_alert.assert_called_once_with(message)
        self.assertEqual(result, skill.handle_reschedule_alert.return_value)
