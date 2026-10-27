"""The alert locks hold across processes and threads, and need no combo-lock."""
import os
import re
import subprocess
import sys
import threading
import time
from importlib.metadata import requires
from pathlib import Path
from tempfile import gettempdir

import pytest
from ovos_utils.fakebus import FakeBus
from ovos_workshop.skills.ovos import OVOSSkill

from ovos_skill_alerts.util.alert_manager import AlertManager, SYNC_LOCK

HOLD_SECONDS = 1.5

HOLDER = f"""
import time
from ovos_skill_alerts.util.alert_manager import SYNC_LOCK
with SYNC_LOCK:
    print("held", flush=True)
    time.sleep({HOLD_SECONDS})
"""


def requirement_names(dist: str) -> set:
    return {re.split(r"[\s;<>=!~\[]", req, maxsplit=1)[0].lower().replace("_", "-")
            for req in requires(dist) or []}


@pytest.fixture
def managers(tmp_path):
    skill = OVOSSkill(skill_id="ovos-skill-alerts", bus=FakeBus())
    noop = (lambda a: None, lambda a: None)
    yield (AlertManager(str(tmp_path / "one"), skill, noop),
           AlertManager(str(tmp_path / "two"), skill, noop))
    skill.default_shutdown()


def test_metadata_requires_filelock_not_combo_lock():
    names = requirement_names("ovos-skill-alerts")
    assert "combo-lock" not in names
    assert "filelock" in names


def test_lock_file_is_the_combo_lock_path():
    # File name that combo-lock 0.3.1 NamedLock("alert_dav_sync") uses.
    expected = Path(gettempdir(), "combo_locks", "YWxlcnRfZGF2X3N5bmM=.lock")
    assert Path(SYNC_LOCK.lock_file) == expected
    with SYNC_LOCK:
        assert os.stat(expected).st_mode & 0o777 == 0o666


def test_other_process_waits_for_release():
    holder = subprocess.Popen([sys.executable, "-c", HOLDER],
                              stdout=subprocess.PIPE, text=True)
    try:
        # The package logs to stdout, so skip lines until the marker.
        assert "held" in (line.strip() for line in holder.stdout)
        start = time.monotonic()
        with SYNC_LOCK:
            waited = time.monotonic() - start
    finally:
        holder.wait(timeout=60)
    assert holder.returncode == 0
    assert waited > HOLD_SECONDS / 2


def test_manager_in_other_thread_waits_for_release(managers):
    first, second = managers
    held = threading.Event()

    def hold():
        with first._read_lock:
            held.set()
            time.sleep(HOLD_SECONDS)

    holder = threading.Thread(target=hold)
    holder.start()
    assert held.wait(timeout=10)
    start = time.monotonic()
    second.missed_alerts
    waited = time.monotonic() - start
    holder.join()
    assert waited > HOLD_SECONDS / 2
