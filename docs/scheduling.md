# How alerts are timed
<!-- agent-hint
covers: how an alert becomes a schedule in the scheduled-events service, and the missed-alert rule
source: util/alert_manager.py
generated: no
verify: grep -q 'ovos-bus-client>=2.11.0a1' pyproject.toml && grep -q 'ovos-workshop>=9.6.4a1' pyproject.toml
see: testing.md
-->

The skill has no clock of its own. The scheduled-events service rings each alert.

## Rules

1. Each alert is one schedule, named by the uuid of the alert. A notification before an event is a second schedule, with the name `<uuid>.pre`.
2. A schedule with the same name replaces the old one. Thus an alert that the skill adds two times is one alert.
3. A one-time alert is a schedule for an instant with a time zone.
4. An alert that repeats at a fixed interval is a period from its first occurrence. A late ring does not move the rest of the series.
5. An alarm on weekdays, and an alert with an end date, get their next occurrence from the skill each time they ring. The skill calculates it in the time zone of the alert, so the alert keeps its wall-clock time across a daylight-saving change.
6. Schedules stay when the skill or the service stops. At start, the skill adds its pending alerts again with the same names.
7. An occurrence that comes more than one minute late goes on the missed list and does not ring. An occurrence that the service could not deliver also goes on the missed list.

The skill needs `ovos-bus-client>=2.11.0a1` and `ovos-workshop>=9.6.4a1`.

---
[← Settings and CalDAV sync](settings.md) · [Home](index.md) · [Run the tests →](testing.md)
