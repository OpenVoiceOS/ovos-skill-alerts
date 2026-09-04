"""Standalone padacioso probe over the en-US golden rows + a theft set.

Not a pytest module (leading underscore) -- run directly:
    .venv/bin/python test/end2end/_gate_probe.py
Loads every .intent/.entity file this skill ships for en-US straight into
a bare padacioso IntentContainer (no MiniCroft/skill boot needed) and
checks every golden row resolves to one of the file(s) implementing its
intent_label, plus a "theft set" of phrases that must NOT be captured by
RescheduleAlert's {time} slot (ChangeMediaProperties' territory).
"""
import json
import re
from pathlib import Path

from padacioso import IntentContainer

ROOT = Path(__file__).resolve().parents[2]
INTENT_DIR = ROOT / "locale" / "en-US" / "intent"
ENTITY_DIR = ROOT / "locale" / "en-US" / "entity"
GOLDEN = ROOT / "test" / "end2end" / "golden_utterances_en-US.jsonl"
TIME_BLACKLIST = ROOT / "locale" / "en-US" / "vocab" / "time.blacklist"

LABEL_TO_FILES = {
    "CancelAlert": {"CancelAlert", "CancelAlert2"},
    "ChangeMediaProperties": {"ChangeMediaProperties"},
    "ChangeProperties": {"ChangePriority", "ChangePriority2", "ChangeRepeat", "ChangeUntil"},
    "CreateAlarmAlt": {"CreateAlarmAlt"},
    "CreateOcpAlarm": {"CreateOcpAlarm"},
    "CreateOcpAlarmAlt": {"CreateOcpAlarmAlt"},
    "DAVSync": {"DAVSync"},
    "ListAlerts": {"ListAlerts", "ListAlerts2", "ListAlerts3"},
    "RescheduleAlert": {"RescheduleAlert", "RescheduleAlert2"},
    "RescheduleAlertAlt": {"RescheduleAlertAlt"},
    "TimerStatus": {"TimerStatus", "TimerStatus2"},
}

THEFT_SET = [
    # ChangeMediaProperties territory that RescheduleAlert's {time} slot
    # must not steal (OVOS-INTENT-2 4.3 slot-blacklist).
    "adjust my reminder to be spoken",
    "change my alarm to playback a file",
    "change the alarm to play music",
    "adjust the reminder to be recorded",
]


def build_container():
    container = IntentContainer()
    for entity_file in sorted(ENTITY_DIR.glob("*.entity")):
        samples = [l.strip() for l in entity_file.read_text().splitlines() if l.strip()]
        container.add_entity(entity_file.stem, samples)
    for intent_file in sorted(INTENT_DIR.glob("*.intent")):
        samples = [l.rstrip("\n") for l in intent_file.read_text().splitlines() if l.strip()]
        container.add_intent(intent_file.stem, samples)
    return container


def main():
    container = build_container()
    rows = [json.loads(l) for l in GOLDEN.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if not r.get("needs_manual")]

    # RescheduleAlert(2) and RescheduleAlertAlt are behaviorally
    # interchangeable -- handle_reschedule_alert_alt just delegates to
    # handle_reschedule_alert (see test_reschedule_alert_alt_delegates_to_
    # reschedule_alert). A raw-padacioso tie/miss between these two labels
    # is not a routing defect.
    EQUIVALENT_LABELS = {
        frozenset({"RescheduleAlert", "RescheduleAlertAlt"}),
    }

    misses = []
    behaviorally_equivalent = []
    for row in rows:
        utterance = row["utterance"]
        expected = LABEL_TO_FILES.get(row["intent_label"], {row["intent_label"]})
        result = container.calc_intent(utterance)
        matched = result.get("name")
        if matched in expected:
            continue
        matched_label = next((l for l, files in LABEL_TO_FILES.items() if matched in files), matched)
        if frozenset({row["intent_label"], matched_label}) in EQUIVALENT_LABELS:
            behaviorally_equivalent.append((utterance, row["intent_label"], matched))
            continue
        misses.append((utterance, row["intent_label"], matched, result.get("conf")))

    print(f"({len(behaviorally_equivalent)} rows crossed RescheduleAlert/RescheduleAlertAlt file "
          f"boundaries but are handler-equivalent -- not counted as misses)")

    print(f"padacioso: {len(rows) - len(misses)}/{len(rows)} golden rows matched their intended file(s)")
    for u, label, matched, conf in misses:
        print(f"  MISS: {u!r} expected={label} got={matched} conf={conf}")

    theft_hits = []
    for utterance in THEFT_SET:
        result = container.calc_intent(utterance)
        matched = result.get("name")
        if matched in ("RescheduleAlert", "RescheduleAlert2"):
            theft_hits.append((utterance, matched, result.get("conf")))

    print(f"theft set: {len(THEFT_SET) - len(theft_hits)}/{len(THEFT_SET)} correctly NOT captured by RescheduleAlert")
    for u, matched, conf in theft_hits:
        print(f"  STOLEN: {u!r} -> {matched} conf={conf}")

    return len(misses), len(theft_hits)


if __name__ == "__main__":
    misses, thefts = main()
    raise SystemExit(1 if (misses or thefts) else 0)
