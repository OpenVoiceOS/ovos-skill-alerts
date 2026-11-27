# How the skill reads times
<!-- agent-hint
covers: how chronologia reads a time or a duration, and the next-occurrence rule for a bare time
source: util/parse_utils.py:_read_timespan
generated: no
verify: .venv/bin/python docs/verify_examples.py
see: numbers.md
-->

The skill reads every time and every length with chronologia. This page shows what an utterance resolves to.

## Example

```python
import datetime as dt
from dateutil.tz import gettz
from ovos_skill_alerts.util.parse_utils import extract_datetime, extract_duration

now = dt.datetime(2026, 11, 27, 10, 0, tzinfo=gettz("Europe/Lisbon"))
extract_datetime("at 8 am", "en-US", now)[0]           # 2026-11-28 08:00
extract_datetime("at 11 am", "en-US", now)[0]          # 2026-11-27 11:00
extract_datetime("tomorrow morning", "en-US", now)[0]  # 2026-11-28 09:00
extract_datetime("às 8 da manhã", "pt-PT", now)[0]     # 2026-11-28 08:00
extract_datetime("um 7 Uhr", "de-DE", now)[0]          # 2026-11-27 19:00
extract_duration("30 minutes", "en-US", now)[0]        # 0:30:00
```

`docs/verify_examples.py` runs these examples and compares each value.

## Rules

1. A bare time goes to its next occurrence. At 10:00, "at 8 am" is 08:00 tomorrow, and "at 11 am" is 11:00 today.
2. A time with no AM or PM goes to the next occurrence on a 12-hour clock. At 10:00, "um 7 Uhr" is 19:00 today.
3. A part of the day with no clock, such as "tomorrow morning" or "tonight", goes to the middle of that part of the day. When the middle has passed, the alert goes to the current time.
4. A span of whole days, such as "tomorrow" or "this week", covers every day in the span. A query such as "which reminders are scheduled today" uses this span.
5. A month or a year in a length is counted on the calendar from now.
6. When you move an alert to a time of day, the alert keeps its own date. "Move the event to 8 pm" keeps the day of the event. "Tomorrow at 8 pm", "tonight at 10" and a time that has passed on that day are read from now.

The skill reads the time in the time zone of the session. Without one, it uses the configured time zone.

---
[← Alert types and phrases](usage.md) · [Home](index.md) · [How the skill speaks numbers →](numbers.md)
