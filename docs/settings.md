# Settings and CalDAV sync
<!-- agent-hint
covers: every skill setting with its default, and the CalDAV credentials file
source: util/config.py:DEFAULT_SETTINGS
generated: no
verify: grep -q '"snooze_mins": 15' util/config.py && grep -q '_DAV_CREDFILE = "dav_credentials.json"' util/dav_utils.py
see: scheduling.md
-->

This page lists the settings in `settings.json` and tells how to connect a CalDAV server.

## Example

```json
{
  "speak_alarm": false,
  "snooze_mins": 10,
  "services": "nextcloud",
  "frequency": 15
}
```

## Settings

| Setting | Default | Effect |
| :--- | :--- | :--- |
| `speak_alarm` | `false` | speak the alarm, or only play the sound when false |
| `speak_timer` | `true` | speak the timer, or only play the sound when false |
| `sound_alarm` | `constant_beep.mp3` | sound file of an alarm |
| `sound_timer` | `beep4.mp3` | sound file of a timer |
| `snooze_mins` | `15` | snooze length when you give no length or time |
| `timeout_min` | `1` | minutes that an alert rings before it goes on the missed list, except for media alarms |
| `play_volume` | `90` | volume of the alert sound, in percent |
| `escalate_volume` | `true` | alarms only: raise the volume in steps of 10 % up to `play_volume` |
| `priority_cutoff` | `8` | priority cutoff of an alert |
| `services` | `""` | CalDAV services to sync, as a comma-separated string |
| `frequency` | `15` | minutes between two syncs |
| `sync_ask` | `false` | ask before the skill syncs a new reminder or todo |

The defaults come from `DEFAULT_SETTINGS` in `util/config.py`. The settings UI in `settingsmeta.yml` shows `timeout_min` as 2.

## Connect a CalDAV server

1. Start the skill once. It writes a template `dav_credentials.json` in its file system folder.
2. Add one entry for each service:

   ```json
   {
     "nextcloud": {
       "url": "https://<host:port>/remote.php/dav",
       "username": "...",
       "password": "...",
       "ssl_verify_cert": "..."
     }
   }
   ```

   Remove `ssl_verify_cert` when the server has no SSL.
3. Put the service names in `services` in `settings.json`.
4. The skill reloads its settings and syncs every `frequency` minutes. Say "synchronize calendars" to sync at once.
5. Say "which calendars are available?" to hear the calendars. When there are more than one, the skill asks which one to use.

Only events, reminders and todos sync. Alarms and timers do not sync. The skill reads events for 365 days ahead. With Nextcloud, turn on the Tasks app to sync todos. The skill speaks connection errors, and the skill log gives the details.

Check the time zone of the server and of each event. A wrong time zone moves the alert.

---
[← How the skill speaks numbers](numbers.md) · [Home](index.md) · [How alerts are timed →](scheduling.md)
