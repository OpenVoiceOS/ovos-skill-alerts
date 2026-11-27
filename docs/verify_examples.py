"""Run the examples in docs/times.md and docs/numbers.md and compare the output."""
import datetime as dt
import sys

from dateutil.tz import gettz

from ovos_skill_alerts.util.locale import spoken_number
from ovos_skill_alerts.util.parse_utils import extract_datetime, extract_duration

anchor = dt.datetime(2026, 11, 27, 10, 0, tzinfo=gettz("Europe/Lisbon"))
TIMES = {
    ("at 8 am", "en-US"): "2026-11-28 08:00",
    ("at 11 am", "en-US"): "2026-11-27 11:00",
    ("tomorrow morning", "en-US"): "2026-11-28 09:00",
    ("às 8 da manhã", "pt-PT"): "2026-11-28 08:00",
    ("um 7 Uhr", "de-DE"): "2026-11-27 19:00",
}
NUMBERS = {
    ("pt-PT", "list_todo_num_deleted"): "um",
    ("pt-PT", "list_todo_lists"): "uma",
    ("es-ES", "list_todo_num_deleted"): "una",
    ("de-DE", "list_todo_lists"): "eine",
    ("da-DK", "list_todo_num_deleted"): "et",
    ("en-US", "list_todo_lists"): "one",
}
FALLBACK = {"fa-IR": "دو"}

failed = 0
for (text, lang), want in TIMES.items():
    got = extract_datetime(text, lang, anchor)[0].strftime("%Y-%m-%d %H:%M")
    failed += got != want
    print(f"{text!r} {lang}: {got} (want {want})")
got = extract_duration("30 minutes", "en-US", anchor)[0]
failed += got != dt.timedelta(minutes=30)
for (lang, dialog), want in NUMBERS.items():
    got = spoken_number(1, lang, dialog)
    failed += got != want
    print(f"1 {lang} {dialog}: {got} (want {want})")
got = spoken_number(1, "sv-SE", ordinal=True)
failed += got != "första"
print(f"1 sv-SE ordinal: {got} (want första)")
for lang, want in FALLBACK.items():
    got = spoken_number(2, lang)
    failed += got != want
    print(f"2 {lang}: {got} (want {want})")
sys.exit(1 if failed else 0)
