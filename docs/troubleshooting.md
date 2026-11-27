# Troubleshooting
<!-- agent-hint
covers: known problems, incompatible skills and support links
source: README.md
generated: no
verify: test -f docs/troubleshooting.md
see: index.md
-->

This page lists known problems and the skills that collide with this skill.

## Known problems

- **The skill does not understand an utterance.** Look in the log for the intent and the transcribed utterance. The STT can give wrong words. Try a different STT service.
- **Missed alerts do not show.** Use the latest `ovos-gui-plugin-shell-companion` and remove `ovos-PHAL-plugin-notification-widgets`. The home screen shows the number of missed alerts in the upper left corner.
- **An "unknown" answer comes after the last list item.** This comes from how the skill reads answers in a response context. The list items are correct.

The skill needs ovos-core 0.0.8 or later. For the GUI, use `skill-ovos-homescreen>=0.0.3a6`.

## Incompatible skills

This skill replaces these skills, and their intents collide. Remove them before you install this skill:

- [skill-reminder.mycroftAI](https://github.com/mycroftai/skill-reminder)
- [skill-alarm.mycroftAI](https://github.com/mycroftai/skill-alarm)
- [mycroft-timer.mycroftAI](https://github.com/mycroftai/mycroft-timer)
- [skill-alerts.NeonGeckoCom](https://github.com/NeonGeckoCom/skill-alerts)

## Support

- [Matrix chat](https://matrix.to/#/!XFpdtmgyCoPDxOMPpH:matrix.org?via=matrix.org)
- [GitHub issues](https://github.com/OpenVoiceOS/ovos-skill-alerts/issues)

---
[← Translations](translations.md) · [Home](index.md)
