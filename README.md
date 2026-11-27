# <img src='./logo.svg' card_color="#FF8600" width="50" style="vertical-align:bottom">Alerts
<!-- agent-hint
covers: what the skill does, install, a quickstart and the docs link table
source: pyproject.toml
generated: no
verify: test -f docs/index.md
see: docs/index.md
-->

An OVOS skill that sets alarms, timers, reminders, events and todo lists by voice. It can sync reminders, events and todos with a CalDAV server.

## Install

```bash
uv pip install --prerelease=allow ovos-skill-alerts
```

Remove the Mycroft alarm, reminder and timer skills first. Their intents collide with this skill.

## Quickstart

```text
"set an alarm for 8 am"                  -> Your alarm is set for eight a.m., in six hours thirty six minutes.
"set a timer for 30 minutes"             -> Timer for thirty minutes, starting now.
"remind me to call mom tomorrow at 9 am" -> Your reminder is set for nine a.m., in one day seven hours.
```

## Documentation

| Page | Contents |
| :--- | :--- |
| [Docs index](docs/index.md) | the reading order |
| [Alert types and phrases](docs/usage.md) | alarms, timers, reminders, events, todo lists |
| [How the skill reads times](docs/times.md) | chronologia and the next-occurrence rule |
| [How the skill speaks numbers](docs/numbers.md) | numtag, noun gender, fallback languages |
| [Settings and CalDAV sync](docs/settings.md) | every setting and the DAV credentials |
| [How alerts are timed](docs/scheduling.md) | schedules, restarts, missed alerts |
| [Run the tests](docs/testing.md) | unit tests, end-to-end tests, golden utterances |
| [Translations](docs/translations.md) | locale files and how to add a language |
| [Troubleshooting](docs/troubleshooting.md) | known problems and support |

## License

[BSD-3-Clause](./LICENSE.md). Credits: [NeonGeckoCom](https://github.com/NeonGeckoCom), [NeonDaniel](https://github.com/NeonDaniel).
