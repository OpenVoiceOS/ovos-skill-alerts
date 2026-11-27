# Alert types and phrases
<!-- agent-hint
covers: the alert types and the example phrases that create, query, change and cancel each one
source: locale/en-US/intent/
generated: no
verify: .venv/bin/python docs/verify_phrases.py >/dev/null 2>&1
see: times.md
-->

This page lists the alert types and the phrases that control them. "Alert" is the general term for all the types.

## Example

These answers come from a run of the skill in en-US:

```text
"set an alarm for 8 am"                    -> Your alarm is set for eight a.m., in <time until the alert>.
"remind me to take out the trash at 7 pm"  -> Your reminder is set for seven p.m., in <time until the alert>.
"remind me to call mom tomorrow at 9 am"   -> Your reminder is set for nine a.m., in <time until the alert>.
"remind me to walk the dog"                -> should i remind you at a specific time?
```

When you give no name, the name of the alert is its time, for example the "8 AM" alarm or the "2 minute" timer.

## Alarms

An alarm rings at a time of day. It can repeat daily or on given weekdays. With a media word, it starts media through OCP.

- "Set an alarm for 8 AM."
- "Set a daily alarm for 8 AM."
- "Set an alarm for 8 AM on saturdays."
- "Wake me up at 8 AM with music." The skill asks for the media title.
- "Wake me with music." This adds media to the next alarm.
- "When is my next alarm?"
- "Cancel my next alarm."

## Timers

A timer counts down a length of time. A timer with no length counts up from the moment you start it. Say "timer stop" to stop it and hear the time that passed.

- "Set a timer for 30 minutes."
- "How much time is left on my timer?"
- "Extend the timer by 2 minutes."
- "Extend the timer until 10 am."

## Reminders and events

A reminder has only a start time. An event can also have an end time. The skill warns you when an event collides with another event, and can give a notification before the event starts.

- "Remind me to take out the trash every Thursday and Sunday at 7 PM."
- "Remind me to take out the trash every day at 7 PM until next saturday."
- "Schedule an appointment for tennis on friday at 2 PM."
- "Move my next event one hour earlier."
- "Are there any events between friday and sunday?"

When you move a recurring alert, the skill asks if the change is for all occurrences or only the next one.

## Todo lists

A todo has no time. You can put todos in named lists, for example a shopping list.

- "Remind me to walk the dog." With no time, the skill asks for a time. Say no to keep it as a todo.
- "Create a shopping list."
- "Add items to the shopping list." Say the items one at a time. Silence stops the recording.
- "Which items are on the shopping list?"
- "Which lists are stored?"
- "Remove all items on the shopping list."
- "Delete the shopping list."

With CalDAV sync on, a removed todo becomes a completed task on the server.

## Active and missed alerts

An active alert is an alert that rings at this moment. The skill reads these phrases while the alert rings, not through an intent:

| Say | Result |
| :--- | :--- |
| Stop alert | the alert stops |
| Snooze | the alert rings again after `snooze_mins` (15 minutes by default) |
| Snooze for 1 minute, or snooze until 8 AM | the alert rings again at that time |
| Remind me again at 10 AM | the alert rings again at that time, without the alert name |

An alert that you do not stop goes on the missed list.

- "Which alert did I miss?"

## Cancel

- "Cancel my 8 AM alarm."
- "Cancel all alarms."
- "Cancel the alarms on saturday."

"Cancel all alerts" also removes all reminders and events. With CalDAV sync on, it removes them on the server too.

## Reference

| Intent file | Function |
| :--- | :--- |
| `create_alarm` | set an alarm, recurring or with media |
| `create_timer` | start a timer |
| `create_reminder` | set a reminder |
| `create_event` | schedule an event |
| `reschedule_alert` | move an alert earlier or later |
| `change_priority` | change the priority of an alert |
| `change_repeat` | change the recurrence |
| `change_until` | change the end date of a recurrence |
| `change_media_properties` | change the media or sound of an alert |
| `list_alerts` | list active alerts, also in a time frame |
| `timer_status` | give the status of the timers |
| `missed_alerts` | read and clear the missed alerts |
| `cancel_alert` | cancel one or more alerts |
| `create_list` | create a todo list |
| `add_list_subitems` | add items to a list |
| `query_list_names` | give the names of the lists |
| `query_list_entries` | read the todos or the items of a list |
| `delete_list_entries` | remove todos or list items |
| `delete_list` | remove a list and its items |
| `calendar_list` | give the CalDAV calendars |
| `dav_sync` | sync with the CalDAV server |

---
[Home](index.md) · [How the skill reads times →](times.md)
