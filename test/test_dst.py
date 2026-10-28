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
Regression tests for repeating alerts drifting by the DST delta once they
cross a spring-forward/fall-back transition.

Root cause: `Alert` used to persist only an ISO timestamp
(`next_expiration_time`); every read re-parsed it with
`datetime.fromisoformat`, which collapses a real (DST-aware) timezone into a
frozen fixed UTC offset. Repeat advancement then added a `timedelta` to that
frozen-offset datetime, so the UTC offset never updated across a transition
and the alert fired an hour early/late forever after.
"""
import datetime as dt
import unittest

from dateutil.tz import gettz

from ovos_skill_alerts.util import EVERYDAY, Weekdays
from ovos_skill_alerts.util.alert import Alert

NEW_YORK = gettz("America/New_York")


class TestDSTRepeatAdvance(unittest.TestCase):
    def test_daily_alarm_spring_forward(self):
        # 2027-03-14 02:00 local is the US spring-forward transition
        # (clocks jump 02:00 -> 03:00). An 8am daily alarm created the day
        # before should still read 8am local (now EDT, UTC-4) afterwards,
        # not drift to what used to be 8am EST (UTC-5).
        first = dt.datetime(2027, 3, 13, 8, 0, tzinfo=NEW_YORK)
        alert = Alert.create(
            expiration=first,
            alert_name="daily alarm",
            repeat_days=set(EVERYDAY),
        )
        self.assertEqual(alert.expiration, first)

        second = alert.advance()
        self.assertEqual(second.hour, 8)
        self.assertEqual(second.minute, 0)
        self.assertEqual(second.date(), dt.date(2027, 3, 14))
        self.assertEqual(second.utcoffset(), dt.timedelta(hours=-4))
        self.assertEqual(second.astimezone(dt.timezone.utc).hour, 12)

    def test_daily_alarm_fall_back(self):
        # 2026-11-01 02:00 local is the US fall-back transition (clocks
        # fall back 02:00 -> 01:00). An 8am daily alarm created the day
        # before should still read 8am local (now EST, UTC-5) afterwards,
        # not drift to what used to be 8am EDT (UTC-4).
        first = dt.datetime(2026, 10, 31, 8, 0, tzinfo=NEW_YORK)
        alert = Alert.create(
            expiration=first,
            alert_name="daily alarm",
            repeat_days=set(EVERYDAY),
        )
        second = alert.advance()
        self.assertEqual(second.hour, 8)
        self.assertEqual(second.minute, 0)
        self.assertEqual(second.date(), dt.date(2026, 11, 1))
        self.assertEqual(second.utcoffset(), dt.timedelta(hours=-5))
        self.assertEqual(second.astimezone(dt.timezone.utc).hour, 13)

    def test_weekly_repeat_across_spring_forward(self):
        # Saturday 8am alarm, one week later crosses the 2027-03-14
        # transition; wall clock must stay 8am.
        first = dt.datetime(2027, 3, 6, 8, 0, tzinfo=NEW_YORK)  # a Saturday
        alert = Alert.create(
            expiration=first,
            alert_name="weekly alarm",
            repeat_days={Weekdays.SAT},
        )
        second = alert.advance()
        self.assertEqual(second.date(), dt.date(2027, 3, 13))  # not yet crossed
        third = alert.advance()
        self.assertEqual(third.date(), dt.date(2027, 3, 20))
        self.assertEqual(third.hour, 8)
        self.assertEqual(third.utcoffset(), dt.timedelta(hours=-4))

    def test_until_window_spanning_transition(self):
        first = dt.datetime(2027, 3, 13, 8, 0, tzinfo=NEW_YORK)
        until = dt.datetime(2027, 3, 20, 8, 0, tzinfo=NEW_YORK)
        alert = Alert.create(
            expiration=first,
            alert_name="limited daily alarm",
            repeat_days=set(EVERYDAY),
            until=until,
        )
        second = alert.advance()
        self.assertEqual(second.hour, 8)
        self.assertEqual(second.utcoffset(), dt.timedelta(hours=-4))

    def test_legacy_serialized_alert_loads_and_fires(self):
        # An alert serialized before `tz_name` was introduced has no such
        # field; it must still deserialize and fire using the frozen
        # fixed-offset recovered from the stored ISO timestamp (the
        # pre-existing, non-DST-aware behavior is the documented backcompat
        # fallback for old data).
        legacy_data = {
            "next_expiration_time": "2027-03-13T08:00:00-05:00",
            "repeat_days": [d.value for d in EVERYDAY],
            "repeat_frequency": None,
            "until": None,
            "alert_name": "legacy daily alarm",
            "alert_type": 0,
            "dav_type": 1,
            "priority": 5,
            "prenotification": None,
            "audio_file": None,
            "context": {"ident": "legacy-1"},
            "dav_calendar": None,
            "dav_service": None,
            "dav_synchron": False,
            "lang": "en-us",
        }
        alert = Alert.from_dict(dict(legacy_data))
        self.assertNotIn("tz_name", alert.data)
        first = alert.expiration
        self.assertIsNotNone(first)
        self.assertEqual(first.utcoffset(), dt.timedelta(hours=-5))

        second = alert.advance()
        self.assertEqual(second.hour, 8)
        # Legacy (pre-fix) behavior: the frozen -05:00 offset is retained
        # even after crossing the DST transition, i.e. the drift bug is
        # preserved for already-serialized alerts rather than silently
        # reinterpreted.
        self.assertEqual(second.utcoffset(), dt.timedelta(hours=-5))


if __name__ == "__main__":
    unittest.main()
