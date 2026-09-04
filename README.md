# <img src='./logo.svg' card_color="#FF8600" width="50" style="vertical-align:bottom" style="vertical-align:bottom">Alerts

## Summary

An OVOS skill that manages alarms, timers, reminders, events, and todos, with optional sync to a CalDAV service.

## Description

The skill creates alarms, timers, reminders, and todo lists. You can remove them by name, time, or type, and ask what is active. If you turn on sync with a DAV server, you can also reach your reminders and todo lists from other devices.

Alarms and reminders can recur daily or weekly. You can snooze an active alert for a set amount of time while it plays. Any alert you do not acknowledge goes on a list of missed alerts, which you can read and clear on request.

If you were away, or your device was off or napping, ask for a summary of what you missed. The number of missed notifications shows in the upper left corner of the home screen.

### Distinction between reminder, event, and todo

<ins>__*Events*__</ins>
<sub>Appointments, gigs, and other items that may (but do not have to) have a start and end time. The skill warns you if an event collides with another one. You can add a prenotification in advance.</sub>

<ins>__*Reminders*__</ins>
<sub>Less formal dates with only a start time.
(You can still set a repeating reminder with an endpoint, for example "remind me to take out the trash every day at 7pm <ins>until</ins> next saturday".)</sub>

<ins>__*Todos*__</ins>
<sub>Items not tied to a time, for short-term memory of things to do. You can organize todos into lists, for example a shopping list.</sub>

<ins>__*Alert*__</ins>
<sub>is the general term that covers all of the types above.</sub>

-----------------------

## Intents

The skill matches utterances with file-based intents (padatious/padacioso), not Adapt keyword intents. Each `.intent` file under `locale/<lang>/intent/` is a set of phrase templates, optionally referencing a `.entity` file for a `{slot}` value list or a `.voc` file for an inline `<keyword>` alternation.

- `CreateAlarm` / `CreateAlarmAlt` — set an alarm, optionally recurring on given weekdays.
- `CreateOcpAlarm` / `CreateOcpAlarmAlt` — set an alarm that plays media through OCP when it fires.
- `CreateTimer` — start a countdown timer.
- `CreateReminder` / `CreateReminderAlt` / `create_reminder_recurring` — set a reminder, optionally recurring.
- `CreateEvent` — schedule an event, with collision and prenotification handling.
- `RescheduleAlert` / `RescheduleAlert2` / `RescheduleAlertAlt` — move an existing alert earlier or later.
- `ChangePriority` / `ChangePriority2` — change an alert's priority.
- `ChangeRepeat` — change an alert's recurrence.
- `ChangeUntil` — change an alert's recurrence end date.
- `ChangeMediaProperties` — change the media/sound an alert plays.
- `ListAlerts` / `ListAlerts2` / `ListAlerts3` — list active alerts, optionally within a timeframe.
- `TimerStatus` / `TimerStatus2` — report the status of active timers.
- `missed_alerts` — report and clear missed alerts.
- `CancelAlert` / `CancelAlert2` — cancel one or more alerts.
- `CreateList` — create a todo list.
- `AddListSubitems` — add items to a todo list.
- `QueryListNames` — list the names of existing todo lists.
- `QueryTodoEntries` / `QueryListEntries` — list the entries of a todo/reminder list.
- `DeleteListEntries` — remove specific entries from a todo list.
- `DeleteList` — delete a todo list and its entries.
- `DeleteTodoEntries` — delete one or more todo entries.
- `CalendarList` — list the CalDAV calendars available for sync.
- `DAVSync` — sync with a configured CalDAV server.

## Scenarios

<ins>Keywords</ins> are underlined, _alert names_ are italic.
If you do not name an alert (like _bread_ timer, _tennis_ event), the name defaults to the time it is set for (for example _8 AM_ alarm, _2 minute_ timer).

### Alarms, Timers, Reminders, Events

*One time* alarms, timers, reminders, or events:
- "<ins>Set</ins> an <ins>alarm</ins> for _8 AM_."
- "<ins>Set</ins> a _bread_ <ins>timer</ins> for 30 minutes."
- "<ins>Schedule</ins> a _tennis_ <ins>event</ins> for 2 PM on friday <ins>spanning</ins> 2 hours."
... _(you can add a prenotification in advance for events)_

<sup>HINT:</sup> _A *timer* started without a time acts as a stop timer, counting up from now.
To stop it and hear the elapsed time, say "Timer stop"._

*Recurring* alarms, reminders, or events:
- "<ins>Set</ins> a <ins>daily</ins> <ins>alarm</ins> for _8 AM_."
- "<ins>Set</ins> an <ins>alarm</ins> for 8 AM on <ins>saturdays</ins>."
- "<ins>remind</ins> me to _take out the trash_ <ins>every</ins> Thursday and Sunday at 7 PM."

*OCP* Alarm:
<sup>(An alarm that triggers the media player; _depends on the OCP capabilities of your device or serving instance_)</sup>
- "<ins>wake</ins> me up at 8 AM with <ins>music</ins>." (in general: "... with {media type}")
<sub>-> the skill asks which media title to play, then looks it up in the media library</sub>
- "<ins>wake</ins> me with <ins>music</ins>." <sub>(_sets media on an already created alarm_; the skill picks the next alarm)</sub>

*Reschedule* an existing alarm, timer, reminder, or event:
<sup>(by duration or fixed time)</sup>

- "<ins>Reschedule</ins> my _8 AM_ <ins>alarm</ins> at 9 AM."
- "<ins>Push</ins> the _tennis_ <ins>event</ins> by one hour."
- "<ins>Move</ins> my <ins>next</ins> <ins>event</ins> one hour <ins>earlier</ins>."
- "<ins>Extend</ins> the _bread_ <ins>timer</ins> by 2 minutes." (or: <ins>Extend</ins> the _bread_ <ins>timer</ins> until 10 am)
- "<ins>Change</ins> the _8 AM_ <ins>alarm</ins> <ins>recurring</ins> only mondays and tuesdays."
- "<ins>Change</ins> _tennis_ <ins>event</ins> <ins>length</ins> to 3 hours."

<sup>HINT:</sup> _If you reschedule the time of a recurring alarm, the skill asks whether the change applies to all occurrences or just the next one._

*Query*:
- "<ins>When</ins> is my <ins>next</ins> <ins>alarm</ins>?"
- "<ins>Which</ins> <ins>reminders</ins> are scheduled today?"
- "<ins>Are there</ins> any <ins>events</ins> between friday <ins>and</ins> sunday?" (also: "between friday 10am <ins>and</ins> 3 pm")
<sub>_running timer_</sub>
- "<ins>How much</ins> time is <ins>left</ins> on my _bread_ <ins>timer</ins>?"

*Cancel*:
- <sup>_specific type/name:_</sup> "<ins>Cancel</ins> my _8 AM_ <ins>alarm</ins>." (in general: "cancel my {name} {type}")
- <sup>_all / of a type_:</sup> "<ins>Cancel</ins> <ins>all</ins> <ins>alerts</ins>." / "<ins>Cancel</ins> <ins>all</ins> <ins>alarms</ins>."
- <sup>_on a specific day_:</sup> "<ins>Cancel</ins> <ins>alerts</ins> on saturday."
- <sup>_in a time period_:</sup> "<ins>Cancel</ins> <ins>alerts</ins> between Friday 8 AM <ins>and</ins> 10 AM."
- <sup>_next_:</sup> "<ins>Cancel</ins> my <ins>next</ins> <ins>alarm</ins>."

<sup>CAUTION:</sup> _Double check before you "cancel all", especially with DAV active, because it drops all reminders and events._

*Active alert* (expired and currently speaking or playing):
- <sup>_dismiss_:</sup> "<ins>Stop alert</ins>."
- <sup>_snooze_:</sup> "<ins>Snooze</ins>." (default snooze is 15 minutes)
- <sup>_duration_:</sup> "<ins>Snooze</ins> for 1 minute." / "<ins>Snooze</ins> until 8 AM."

<sup>HINT:</sup> _You can also snooze an active reminder or timer with "<ins>remind me again</ins> at 10 AM." or "<ins>extend by</ins> 2 minutes".
Do not name the alert in this case. The skill always treats active alerts as directly editable._

*Missed alerts* (expired and not acknowledged):

- "<ins>Which alert did i miss?</ins>"
- "<ins>Missed any alerts?</ins>"

### Todo

- [x] walk the dog
- [ ] shopping
  - [ ] milk
  - [ ] toast

_(If you use Nextcloud as the DAV server, turn on the "Tasks" plugin application.)_

_*Create:*_<sub>
- "<ins>Remind</ins> me to _walk the dog_"
- "<ins>create</ins> a _shopping_ <ins>list</ins>" (you can populate the list afterward)

_*Sublist:*_
- "<ins>add</ins> <ins>items</ins> to the _shopping_ <ins>list</ins>" -> _set the items one by one: for example milk <sup>*pling*</sup> toast <sup>*pling*</sup> ..._ <sup>_(silence stops recording)_</sup>
<sup>_(the skill shows or voices the list in advance)_</sup>

_*Complete todos:*_
- "<ins>scratch</ins> milk <ins>entry</ins> from the _shopping_ <ins>list</ins>"
- <sup>_Optionally remove one or more items; the skill shows or voices the list:_</sup> "<ins>remove</ins> <ins>item(s)</ins> from the _shopping_ <ins>list</ins>"
- <ins>Remove</ins> <ins>all</ins> <ins>items</ins> on the _shopping_ <ins>list</ins>
- <ins>Remove</ins> _shopping_ <ins>list</ins>
<sub>_the same commands work for non-list todos:_</sub>
- "<ins>remove</ins> _walk the dog_ <ins>note</ins>"
- "<ins>remove</ins> <ins>todo</ins> entr(y/ies)"
- "<ins>remove</ins> <ins>all</ins> <ins>memos</ins>"

(with DAV active, the server marks the item as complete)

_Query:_
* <sup>_list names :_</sup> "<ins>which</ins> <ins>lists</ins> are stored?" _... "shopping"_
* <sup>_list items :_</sup> "<ins>which</ins> <ins>items</ins> are on the _shopping_ <ins>list</ins>?" _... "milk and toast"_
* <sup>_todo items :_</sup> "<ins>Anything</ins> <ins>todo</ins>?" _... "i should remind you to walk the dog"_

### DAV
_Calendar names:_
- <ins>which</ins> <ins>calendars</ins> are <ins>available</ins>?

_Sync:_ (runs automatically every x minutes by default; you can also trigger it manually)
- <ins>synchronize</ins> <ins>calendars</ins>


---------

## Settings

<sup>_(this is the default)_</sup>
```python
{
    "speak_alarm": false,                              # if the alarm should be spoken
    "speak_timer": true,                               # if the timer should be spoken
    "sound_alarm": "<path/to/soundfile>",              # default constant_beep.mp3
    "sound_timer": "<path/to/soundfile>",              # default beep4.mp3
    "snooze_mins": 15,                                 # default snooze time if duration/time is not specified
    "timeout_min": 1,                                  # the duration the user is notified, after which the alert is considered missed
                                                       # (doesn't apply to media -radio/video/..- alarms)
    "play_volume": 90,                                 # volume of the alert sound
    "escalate_volume": true,                           # alarms only - raise volume over time (10% steps, dependent on timeout_min;
                                                       #                                       half the time on max volume = `play_volume`)
    "priority_cutoff": 8
    ...
}
```
See DAV settings below.

## Setting up a DAV connection
(tested with NextCloud)

For now, you must edit the credential file by hand; this will change in the future.
When the skill starts, it creates a template file at `~/.local/share/mycroft/filesystem/skills/<skillname>/dav_credentials.json`.

```python
{
    "<service>": {
        "url": "https://<ip:port>/remote.php/dav",
        "username": "...",
        "password": "...",
        "ssl_verify_cert": "..."                       # if SSL is set up, otherwise delete this line
    },
    "<another service>": ...
}
```

First set up the credentials, then fill in the matching parts of the skill settings file `settings.json`.
The skill reloads its settings and starts the repeating sync event (every `frequency` seconds).
```python
{
    ...,
    "services": "<service>,<another service>",         # comma separated string of services
    "frequency": 15,                                   # the number of minutes between syncronisation; default 15
    "sync_ask": false                                  # If it should be asked if a generated reminder/todo element should be synchronized
}
```

The skill fetches DAV calendar dates one year in advance.
You can set up multiple calendars on the server; the skill asks which one to sync to.
Connection errors are voiced; check the skill log for details.

Only events, reminders, and todos sync. Alarms and timers do not sync.
Check the timezone on your server and events, because the skill sometimes reads the timezone wrong and schedules the alert incorrectly.

## Known Bugs / Troubleshooting

_This skill targets ovos-core >= 0.0.8 and its dependencies. On an older version, you might run into major problems; please update.
The skill is tested mainly in German and, to a lesser extent, English, and might miss some individual speech patterns. Other languages are autotranslated and need review. During the alpha phase, contributions are welcome to build a well balanced experience across languages._

- __The skill does not understand or misreads what I am saying.__
_Check the logs for the intent that fired and the utterance that was transcribed. STT might have gotten the words wrong. Try a different service (a known issue especially with non-English speakers using Whisper)._
- __The notification system does not work properly. Missed alerts do not show.__
_Notifications sometimes get mixed up; this is a known issue and work is in progress. Use the latest `ovos-gui-plugin-shell-companion` ([#](https://github.com/OpenVoiceOS/ovos-gui-plugin-shell-companion)) and remove the old `ovos-PHAL-plugin-notification-widgets`._
- __When you populate a list, the last item is followed by an "unknown" utterance.__
_This is a known issue that a future release will fix. It comes from how the skill handles input in a response context. It is not critical and you can ignore it; the list still populates correctly most of the time._

## Recommended Versions
These are not hard requirements, since preferences vary, but recommended.
GUI: `skill-ovos-homescreen >= 0.0.3a6` (see also this [pending PR](https://github.com/OpenVoiceOS/skill-ovos-homescreen/pull/92))

## Incompatible Skills
This skill has known intent collisions with, and replaces:
- [skill-reminder.mycroftAI](https://github.com/mycroftai/skill-reminder)
- [skill-alarm.mycroftAI](https://github.com/mycroftai/skill-alarm)
- [mycroft-timer.mycroftAI](https://github.com/mycroftai/mycroft-timer)
- [skill-alerts.NeonGeckoCom](https://github.com//skill-alerts)

Remove these skills before you install this one.

## Contributing Translations
Most of the skill is autotranslated, except for English and German, and needs review.
Intent matching is file-based (padatious/padacioso), not Adapt: each `.intent` file under `locale/<lang>/intent/` lists phrase templates, `{slot}` placeholders are optionally backed by a sibling `.entity` file, and a `<keyword>` reference inlines the matching alternation from a sibling `.voc` file.

A handful of `.voc` files (for example `until.voc`, `priority.voc`, `repeat.voc`, `days.voc`) are also read directly at runtime by the skill's own keyword-matching helpers, to recognize a concept anywhere in free text rather than through a fixed template slot.
Dialogs are mostly straightforward and should include the correct mustache tags from the start.
Keep these patterns in mind.

To contribute a translation, check the `intent`, `entity`, `vocab`, and `dialog` folders and add the files for your language, mirroring the structure of an existing locale (`en-US` or `de-DE`).
For questions, contact @sgee_ in Matrix chat.

## Contact Support
Use [this link (Matrix Chat)](https://matrix.to/#/!XFpdtmgyCoPDxOMPpH:matrix.org?via=matrix.org) or
[submit an issue on GitHub](https://github.com/OpenVoiceOS/skill-alerts/issues).

## Related Projects
- [OpenVoiceOS/ovos-gui-plugin-shell-companion](https://github.com/OpenVoiceOS/ovos-gui-plugin-shell-companion) — shows missed-alert notifications on the home screen.
- [OpenVoiceOS/skill-ovos-homescreen](https://github.com/OpenVoiceOS/skill-ovos-homescreen) — recommended homescreen GUI for this skill.

## License
[BSD-3-Clause](./LICENSE.md)

## Credits
[NeonGeckoCom](https://github.com/NeonGeckoCom)
[NeonDaniel](https://github.com/NeonDaniel)

## Category
**Productivity**
Daily

## Tags
#OVOS
#OpenVoiceOS
#alert
#alarm
#timer
#reminder
#schedule
