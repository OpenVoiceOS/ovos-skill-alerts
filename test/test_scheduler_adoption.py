"""End-to-end checks that alert timing is owned by the scheduled-events service.

Every test wires a real ``ScheduledEventService`` to a ``FakeBus`` with a real
store on disk and drives a real ``AlertManager`` through a real skill, so what
is under test is the round trip a running assistant makes: the skill asks for a
schedule with the scheduling methods every skill has, the service persists it,
a later process picks the store back up and the skill hears the alert ring.

Nothing here reaches for the scheduler client. The skill's own
``schedule_event``, ``schedule_repeating_event`` and ``cancel_scheduled_event``
are the whole of the interface between the two sides, which is the point: the
alert domain stays in the skill and the timing lives in the service.

The service's clock is faked so that a restart, a stretch of downtime and a
daylight-saving transition can happen between two statements. The alerts keep
the real clock, so their expirations are set relative to it and the fake clock
starts there too.
"""

import datetime as dt
import json
import os
import time
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
from ovos_bus_client.util.scheduled_events import ScheduledEventService
from ovos_utils.fakebus import FakeBus
from ovos_workshop.skills.ovos import OVOSSkill

from ovos_skill_alerts.util import AlertType, Weekdays
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.alert_manager import AlertManager, SCHEDULER_MISSED

SKILL_ID = "ovos-skill-alerts"
LISBON = ZoneInfo("Europe/Lisbon")

# Europe/Lisbon springs forward on the 30th of March 2031 and falls back on the
# 26th of October, both Sundays, so a weekday alarm straddles each one.
BEFORE_GAP = dt.datetime(2031, 3, 26, 6, 0, tzinfo=dt.timezone.utc)
BEFORE_OVERLAP = dt.datetime(2031, 10, 22, 6, 0, tzinfo=dt.timezone.utc)


class Clock:
    """The wall clock the service reads, under the test's control."""

    def __init__(self, start: dt.datetime):
        self.now = start

    def advance(self, **delta):
        self.now += dt.timedelta(**delta)


class Assistant:
    """One run of the skill: a bus, the service, a skill and its alerts.

    Building a second one on the same home is a restart of everything, which
    is the situation almost every one of these tests is about.
    """

    def __init__(self, home: str, clock: Clock):
        self.home = home
        self.clock = clock
        self.bus = FakeBus()
        self.expired = []
        self.prenotified = []
        self.missed_reports = []
        self.bus.on(SCHEDULER_MISSED, self.missed_reports.append)
        self.service = ScheduledEventService(
            self.bus, store_path=os.path.join(home, "schedule.json"),
            autostart=False)
        self.skill = OVOSSkill(skill_id=SKILL_ID, bus=self.bus)
        self.manager = AlertManager(
            home, self.skill, (self.prenotified.append, self.expired.append))

    def start(self):
        """Replay the store, the way the service does when it comes up."""
        self.service.replay()
        return self

    def stop(self):
        self.skill.default_shutdown()

    def run_until(self, moment: dt.datetime):
        self.clock.now = moment
        self.service.tick()

    def schedule_ids(self):
        return sorted(schedule.record["id"]
                      for schedule in self.service.all_schedules())

    def await_schedules(self, *ids):
        """Wait for the skill's requests to reach the service.

        A skill's scheduling call does not block it and does not report back,
        so a test that means to look at the result waits for it to be there.
        """
        expected = sorted(ids)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and self.schedule_ids() != expected:
            time.sleep(0.05)
        assert self.schedule_ids() == expected

    def await_next_occurrence(self, ident):
        """Wait until the schedule agrees with the alert's next occurrence."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.next_occurrence(ident) == \
                    self.manager.pending_alerts[ident].expiration:
                return
            time.sleep(0.05)
        assert self.next_occurrence(ident) == \
            self.manager.pending_alerts[ident].expiration

    def await_missed(self, *idents):
        """Wait for the missed-alert reports to reach the bus handler and for
        the manager's own subscriber to have filed them as missed.

        A single tick can report an occurrence missed with nothing in its
        ``missed`` list yet, the way a live scheduler's own housekeeping tick
        would; the manager correctly ignores that one and waits for a later
        tick to settle it, so the wait here keeps ticking the service instead
        of just watching for a report that may never repeat on its own.
        """
        expected = set(idents)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (
                {report.data["id"] for report in self.missed_reports} != expected
                or set(self.manager.missed_alerts) != expected):
            self.service.tick()
            time.sleep(0.05)
        assert {report.data["id"]
                for report in self.missed_reports} == expected
        assert set(self.manager.missed_alerts) == expected

    def next_occurrence(self, ident):
        for schedule in self.service.all_schedules():
            if schedule.record["id"] == ident:
                return dt.datetime.fromisoformat(
                    schedule.record["every"]["start"])
        return None


@pytest.fixture
def clock():
    return Clock(dt.datetime.now(dt.timezone.utc))


@pytest.fixture
def assistant(tmp_path, clock):
    """A factory for successive runs of the skill against one store."""
    home = str(tmp_path)
    runs = []

    def run():
        runs.append(Assistant(home, clock))
        return runs[-1]

    with patch.object(ScheduledEventService, "now",
                      staticmethod(lambda: clock.now)):
        yield run
    for assistant in runs:
        assistant.stop()


def alarm(when: dt.datetime, name: str = "wake up", **kwargs) -> Alert:
    return Alert.create(expiration=when, alert_name=name,
                        alert_type=AlertType.ALARM, **kwargs)


def test_alarm_survives_a_restart_and_fires_exactly_once(assistant, clock):
    first = assistant().start()
    ident = first.manager.add_alert(alarm(clock.now + dt.timedelta(minutes=2)))
    first.await_schedules(ident)
    first.stop()

    second = assistant().start()
    second.await_schedules(ident)
    assert second.expired == [], "an alarm not yet due must not ring on load"

    second.run_until(clock.now + dt.timedelta(minutes=2, seconds=30))
    second.service.tick()

    assert [alert.ident for alert in second.expired] == [ident]
    assert second.schedule_ids() == [], \
        "a one-shot is spent once it has rung"


def test_alarm_due_during_downtime_is_reported_missed(assistant, clock):
    first = assistant().start()
    ident = first.manager.add_alert(alarm(clock.now + dt.timedelta(minutes=2)))
    first.await_schedules(ident)
    first.stop()

    clock.advance(minutes=30)
    second = assistant()
    second.await_schedules(ident)
    second.start()
    second.service.tick()
    second.await_missed(ident)

    assert second.expired == [], \
        "an alarm half an hour late must not ring out of the blue"
    assert {report.data["id"] for report in second.missed_reports} == {ident}
    assert ident in second.manager.missed_alerts
    assert ident not in second.manager.pending_alerts


@pytest.mark.parametrize("start, first_alarm, expected", [
    # the spring-forward: Thursday and Friday at UTC+0, then Monday at UTC+1
    (BEFORE_GAP, dt.datetime(2031, 3, 27, 7, 30, tzinfo=LISBON),
     [("2031-03-27 07:30", dt.timedelta(0)),
      ("2031-03-28 07:30", dt.timedelta(0)),
      ("2031-03-31 07:30", dt.timedelta(hours=1))]),
    # the fall-back: Thursday and Friday at UTC+1, then Monday at UTC+0
    (BEFORE_OVERLAP, dt.datetime(2031, 10, 23, 7, 30, tzinfo=LISBON),
     [("2031-10-23 07:30", dt.timedelta(hours=1)),
      ("2031-10-24 07:30", dt.timedelta(hours=1)),
      ("2031-10-27 07:30", dt.timedelta(0))]),
])
def test_weekday_alarm_keeps_its_wall_clock_across_dst(assistant, clock, start,
                                                       first_alarm, expected):
    clock.now = start
    run = assistant().start()
    ident = run.manager.add_alert(alarm(
        first_alarm, timezone="Europe/Lisbon",
        repeat_days={Weekdays.MON, Weekdays.TUE, Weekdays.WED,
                     Weekdays.THU, Weekdays.FRI}))
    run.await_next_occurrence(ident)

    for wall_clock, _ in expected:
        run.run_until(dt.datetime.strptime(wall_clock, "%Y-%m-%d %H:%M")
                      .replace(tzinfo=LISBON) + dt.timedelta(seconds=5))
        run.await_next_occurrence(ident)

    rang_at = [alert.expiration.astimezone(LISBON) for alert in run.expired]
    assert [(when.strftime("%Y-%m-%d %H:%M"), when.utcoffset())
            for when in rang_at] == expected


def test_dav_sync_survives_a_restart_and_keeps_its_period(assistant, clock,
                                                          tmp_path):
    credentials = {"nextcloud": {"url": "https://dav.example.org/",
                                 "username": "user", "password": "secret",
                                 "ssl_verify_cert": ""}}
    (tmp_path / "dav_credentials.json").write_text(json.dumps(credentials))

    first = assistant().start()
    with patch("ovos_skill_alerts.util.alert_manager.caldav.DAVClient", Mock()):
        first.manager.init_dav_clients(["nextcloud"], frequency=10,
                                       test_connectivity=False)
    first.await_schedules("alerts.sync_dav")
    first.stop()

    clock.advance(minutes=3)
    second = assistant().start()
    assert second.schedule_ids() == ["alerts.sync_dav"], \
        "housekeeping must outlive the process that asked for it"

    fired = []
    second.bus.on(f"{SKILL_ID}.alerts.sync_dav", fired.append)
    with patch("ovos_skill_alerts.util.alert_manager.caldav.DAVClient", Mock()):
        second.manager.init_dav_clients(["nextcloud"], frequency=10,
                                        test_connectivity=False)
    second.await_schedules("alerts.sync_dav")

    second.run_until(clock.now + dt.timedelta(minutes=11))
    assert len(fired) == 1, "one period, one sync"
    assert second.schedule_ids() == ["alerts.sync_dav"]


def test_cancel_reaches_a_schedule_no_handler_is_attached_to(assistant, clock):
    first = assistant().start()
    ident = first.manager.add_alert(alarm(clock.now + dt.timedelta(hours=3)))
    first.await_schedules(ident)
    first.stop()

    second = assistant().start()
    second.await_schedules(ident)
    # a process that knows the alert but is not subscribed to its fired event
    second.skill.event_scheduler.events.clear()

    second.manager.rm_alert(ident)
    second.await_schedules()
    second.stop()

    assert assistant().start().schedule_ids() == [], \
        "a cancelled alert must not come back with the store"


def test_adding_the_same_alert_twice_leaves_one_schedule(assistant, clock):
    first = assistant().start()
    pending = alarm(clock.now + dt.timedelta(minutes=5))
    ident = first.manager.add_alert(pending)
    first.await_schedules(ident)
    first.stop()

    # the skill restarts between writing its cache and finishing the add, so
    # the same alert is offered to the scheduler a second time
    second = assistant().start()
    assert second.manager.add_alert(Alert.deserialize(pending.serialize)) == ident
    second.await_schedules(ident)

    second.run_until(clock.now + dt.timedelta(minutes=5, seconds=30))
    second.service.tick()
    assert [alert.ident for alert in second.expired] == [ident]


def test_reoffering_a_pending_alert_on_load_keeps_its_message_context(
        assistant, clock):
    """A restart must not strip a satellite's routing identity.

    ``reschedule_pending_alerts`` runs at ``AlertManager`` construction with
    no message in flight, so if the alert does not carry its own creating
    context forward the scheduler's stored record loses whatever session and
    source it was made with — every alarm from a satellite would answer as
    the local default after every skill restart.
    """
    satellite_context = {
        "session": {"session_id": "abc123:def456", "site_id": "satA"},
        "source": "satA::1::satA::ec9df8c0",
        "destination": "HiveMind",
    }
    def find_record(run):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for schedule in run.service.all_schedules():
                if schedule.record["id"].endswith(ident):
                    return schedule.record
            time.sleep(0.05)
        raise AssertionError(f"no schedule for {ident} showed up")

    first = assistant().start()
    ident = first.manager.add_alert(alarm(
        clock.now + dt.timedelta(minutes=5),
        message_context=dict(satellite_context)))
    find_record(first)
    first.stop()

    second = assistant().start()
    record = find_record(second)

    assert record["context"].get("session", {}).get("session_id") == \
        "abc123:def456"
    assert record["context"].get("source") == satellite_context["source"]


def test_dav_import_schedules_with_an_empty_context(assistant, clock):
    """A CalDAV-imported alert must not inherit a stray session.

    It is never created from a bus message, so unlike a spoken alarm it has
    no routing identity of its own to hand back on re-offer. ``dig_for_message``
    walks the call stack for a ``Message`` argument, and a DAV sync typically
    runs inline inside the intent handler that configured the calendar, so
    without an explicit empty context the alert would be scheduled with
    that handler's own session instead of a neutral one.
    """
    from ovos_bus_client.message import Message
    from ovos_skill_alerts.util.alert import Alert

    def configure_calendar(message: Message):
        # runs in the same call stack as the intent handler, the way a
        # DAV sync triggered by "connect my calendar" would
        ical_vevent = [
            ("BEGIN", b"VEVENT"),
            ("SUMMARY", "dav alert"),
            ("DTSTART", (clock.now + dt.timedelta(minutes=5)).astimezone()),
            ("DTSTAMP", clock.now.astimezone()),
            ("UID", "dav-ident"),
            ("DAV_CALENDAR", "testcalendar"),
            ("DAV_SERVICE", "testservice"),
        ]
        alert = Alert.from_ical(ical_vevent)
        assert alert.message_context == {}
        return run.manager.add_alert(alert)

    run = assistant().start()
    configuring_message = Message(
        "configure_dav_calendar",
        context={"session": {"session_id": "dav-configurer-session"},
                 "source": "the-configurer"})
    ident = configure_calendar(configuring_message)

    def find_record():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for schedule in run.service.all_schedules():
                if schedule.record["id"].endswith(ident):
                    return schedule.record
            time.sleep(0.05)
        raise AssertionError(f"no schedule for {ident} showed up")

    record = find_record()
    assert record["context"].get("session", {}).get("session_id") != \
        "dav-configurer-session"
    assert record["context"].get("source") != "the-configurer"


def test_build_alert_from_intent_captures_the_message_context():
    """The alert must hold the creating message's context verbatim.

    The rest of the fix has nothing to persist if the alert was never handed
    the routing identity of the message that created it.
    """
    from ovos_bus_client.message import Message
    from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

    satellite_context = {
        "session": {"session_id": "abc123:def456", "site_id": "satA"},
        "source": "satA::1::satA::ec9df8c0",
    }
    message = Message(
        "recognizer_loop:utterance",
        data={"utterance": "set an alarm for 5 minutes from now",
              "utterances": ["set an alarm for 5 minutes from now"],
              "lang": "en-us"},
        context=satellite_context)

    alert = build_alert_from_intent(message)

    assert alert is not None
    assert alert.message_context.get("session", {}).get("session_id") == \
        "abc123:def456"
    assert alert.message_context.get("source") == satellite_context["source"]
