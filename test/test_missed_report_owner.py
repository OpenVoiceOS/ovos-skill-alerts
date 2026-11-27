"""Which missed-occurrence reports the AlertManager files as its own.

ovos-bus-client names the schedule's owner ``skill_id`` in an
``ovos.scheduler.missed`` report; releases before
OpenVoiceOS/ovos-bus-client#351 named it ``owner``. A report keyed either way
must file the alert as missed, and a report naming another skill must not.
"""
import datetime as dt

import pytest
from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus
from ovos_workshop.skills.ovos import OVOSSkill

from ovos_skill_alerts.util import AlertType
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.alert_manager import AlertManager, SCHEDULER_MISSED

SKILL_ID = "ovos-skill-alerts"


@pytest.fixture
def manager(tmp_path):
    bus = FakeBus()
    skill = OVOSSkill(skill_id=SKILL_ID, bus=bus)
    yield AlertManager(str(tmp_path), skill, (lambda a: None, lambda a: None))
    skill.default_shutdown()


def _pending_alarm(manager):
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
    return manager.add_alert(Alert.create(expiration=when,
                                          alert_name="wake up",
                                          alert_type=AlertType.ALARM))


def _report(manager, ident, **owner):
    manager._skill.bus.emit(Message(SCHEDULER_MISSED, {
        "id": ident, "missed": ["2026-10-15T14:00:00+00:00"],
        "fired_late": [], "truncated": False, "next": None, **owner}))


@pytest.mark.parametrize("key", ["skill_id", "owner"])
def test_a_report_naming_this_skill_files_the_alert_as_missed(manager, key):
    ident = _pending_alarm(manager)
    _report(manager, ident, **{key: SKILL_ID})
    assert ident in manager.missed_alerts
    assert ident not in manager.pending_alerts


def test_a_report_naming_another_skill_leaves_the_alert_pending(manager):
    ident = _pending_alarm(manager)
    _report(manager, ident, skill_id="another-skill")
    assert ident not in manager.missed_alerts
    assert ident in manager.pending_alerts
