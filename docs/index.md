# ovos-skill-alerts documentation
<!-- agent-hint
covers: the reading order of the docs and one line for each page
source: docs/
generated: no
verify: diff <(ls docs/*.md | grep -v index.md | xargs -n1 basename | sort) <(grep -o '([a-z0-9-]*\.md)' docs/index.md | tr -d '()' | sort -u)
see: ../README.md
-->

The skill sets alarms, timers, reminders, events and todo lists by voice, and can sync reminders, events and todos with a CalDAV server.

## Quickstart

```bash
uv pip install --prerelease=allow ovos-skill-alerts
```

Say "set an alarm for 8 am". The skill answers:

```text
Your alarm is set for eight a.m., in six hours thirty six minutes.
```

## Pages

| Page | What you get there |
| :--- | :--- |
| [Alert types and phrases](usage.md) | what each alert type does, and the phrases that create, query, change and cancel it |
| [How the skill reads times](times.md) | how chronologia reads a time or a length, and why a bare time goes to its next occurrence |
| [How the skill speaks numbers](numbers.md) | how numtag spells counts and ordinals in the gender of the noun, and the fallback languages |
| [Settings and CalDAV sync](settings.md) | every setting with its default, and how to connect a CalDAV server |
| [How alerts are timed](scheduling.md) | how an alert becomes a schedule, and what happens to a missed occurrence |
| [Run the tests](testing.md) | the unit tests, the end-to-end tests and the golden utterance files |
| [Translations](translations.md) | the locale files, and how to add or fix a language |
| [Troubleshooting](troubleshooting.md) | known problems, incompatible skills and support links |
