# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
Regression tests for session-first timezone sourcing.

A satellite/client can carry its own location preferences on the Session
(`Session.location_preferences`, see ovos-bus-client) rather than the
device-wide `Configuration()`. Before this fix, `build_alert_from_intent`
(and the other user-facing time decisions in this skill) always read the
global config timezone via `get_default_tz()` and ignored the session
entirely, so a satellite user in a different timezone than the box got an
alarm anchored to the box's wall clock instead of their own.
"""
import datetime as dt
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_skill_alerts.util.config import get_session_tz
from ovos_skill_alerts.util.parse_utils import build_alert_from_intent

UTTERANCE = "set an alarm for 8 am"


def session_message(utterance: str, tz_code: str = None) -> Message:
    """
    Build an intent Message carrying a Session with the given IANA
    timezone code in its location preferences (or no session-level
    timezone override at all, when `tz_code` is None), replacing the dead
    `change_user_tz` helper this test used to rely on (it wrote a legacy
    `user_profiles` context shape that nothing in the skill ever reads;
    the real precedence -- session location_prefs first, config second --
    lives on `SessionManager.get(message).timezone`).
    """
    message = Message("intent", {"utterance": utterance, "lang": "en-US"})
    location_prefs = {"timezone": {"code": tz_code}} if tz_code else {}
    session = Session(location_prefs=location_prefs)
    message.context["session"] = session.serialize()
    return message


class TestSessionTimezoneSourcing(unittest.TestCase):
    def test_two_sessions_different_tz_produce_different_utc_instants(self):
        # Same utterance, two satellites in different timezones: each
        # alarm must fire at 8am THEIR local wall clock, which are two
        # different points in UTC time.
        ny_message = session_message(UTTERANCE, "America/New_York")
        tokyo_message = session_message(UTTERANCE, "Asia/Tokyo")

        ny_alert = build_alert_from_intent(ny_message)
        tokyo_alert = build_alert_from_intent(tokyo_message)

        self.assertIsNotNone(ny_alert)
        self.assertIsNotNone(tokyo_alert)

        self.assertEqual(ny_alert.expiration.hour, 8)
        self.assertEqual(tokyo_alert.expiration.hour, 8)

        self.assertNotEqual(
            ny_alert.expiration.astimezone(dt.timezone.utc),
            tokyo_alert.expiration.astimezone(dt.timezone.utc),
            "alarms created under different session timezones resolved to "
            "the same UTC instant -- session timezone was ignored",
        )

        # The satellite's own IANA name is what gets persisted, so the
        # alert keeps that wall clock permanently (also across DST).
        self.assertEqual(ny_alert.data.get("tz_name"), "America/New_York")
        self.assertEqual(tokyo_alert.data.get("tz_name"), "Asia/Tokyo")

    def test_session_without_tz_falls_back_to_config(self):
        # A session that carries no location preferences at all must not
        # break anything: existing (device-config) behavior is preserved.
        message = session_message(UTTERANCE, tz_code=None)
        alert = build_alert_from_intent(message)

        self.assertIsNotNone(alert)
        self.assertEqual(alert.expiration.hour, 8)
        self.assertEqual(alert.expiration.tzinfo, get_session_tz(None))

    def test_get_session_tz_prefers_session_over_config(self):
        # Resolves to the session's own Lisbon timezone, regardless of
        # whatever the ambient device config happens to be in this test
        # environment.
        from dateutil.tz import gettz
        message = session_message(UTTERANCE, "Europe/Lisbon")
        self.assertEqual(get_session_tz(message), gettz("Europe/Lisbon"))

    def test_get_session_tz_no_message_falls_back_to_config(self):
        from ovos_config.locale import get_default_tz
        self.assertEqual(get_session_tz(None), get_default_tz())


if __name__ == "__main__":
    unittest.main()
