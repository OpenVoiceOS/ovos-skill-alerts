from dateutil.tz import gettz
import datetime as dt
from typing import List, Optional

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager
from ovos_config.config import Configuration
from ovos_config.locale import get_default_tz
from ovos_utils.file_utils import resolve_resource_file

DEFAULT_SETTINGS = {
    "speak_alarm": False,
    "speak_timer": True,
    "sound_alarm": "constant_beep.mp3",
    "sound_timer": "beep4.mp3",
    "snooze_mins": 15,
    "timeout_min": 1,
    "play_volume": 90,
    "escalate_volume": True,
    "priority_cutoff": 8,
    "services": "",
    "frequency": 15,
    "sync_ask": False
}


def get_session_tz(message: Optional[Message] = None) -> dt.tzinfo:
    """
    Resolve the timezone to use for a user-facing time decision.

    A satellite/client can override the global configuration by sending its
    own location preferences on the session (`Session.location_preferences`,
    see ovos-bus-client). Those preferences take precedence over the
    device-wide config so that a satellite-created alert keeps the
    satellite's own wall clock rather than the box's. When no message is
    given, or the session carries no timezone, this falls back to the
    global `location.timezone.code` from Configuration.
    :param message: Message associated with the request, if available
    :returns: tzinfo to anchor the alert/time computation to
    """
    if message is not None:
        tz_code = SessionManager.get(message).timezone
        if tz_code:
            tz = gettz(tz_code)
            if tz is not None:
                return tz
    return get_default_tz()


def use_24h_format() -> bool:
    return Configuration()["time_format"] == "full"


def get_date_format() -> str:
    return Configuration()["date_format"]


def find_resource_file(name: str, extensions: List[str] = None):
    name = name.lower()
    if extensions is None:
        extensions = []
    for ext in extensions:
        filename = resolve_resource_file(f"{name}.{ext}")
        if filename:
            return filename
    else:
        return resolve_resource_file(name)
