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

from datetime import datetime

from ovos_date_parser import nice_duration, nice_time
from ovos_utils.log import LOG

from ovos_skill_alerts.util.alert import Alert, AlertType
from ovos_skill_alerts.util.locale import get_abbreviation, translate, datetime_display
from ovos_skill_alerts.util.config import use_24h_format


def build_gui_data(alert: Alert) -> dict:
    if alert.alert_type == AlertType.TIMER:
        return build_timer_data(alert)
    elif alert.alert_type == AlertType.ALARM:
        return build_alarm_data(alert)
    else:
        raise LOG.error(f"Not able to build GUI data for type {alert.alert_type}")


def build_timer_data(alert: Alert) -> dict:
    """
    Parse an alert object into a dict data structure for a timer UI
    """
    if alert.alert_type != AlertType.TIMER:
        raise ValueError(f"Expected a timer, got: {alert.alert_type.name}")

    # TODO There is a unittest assigning datetime instead of isoformat
    # this is not used anywhere else
    start_time = alert.context.get('start_time') or datetime.now(alert.timezone)
    delta_seconds = alert.time_to_expiration
    if delta_seconds.total_seconds() < 0:
        percent_remaining = 0
        human_delta = '-' + nice_duration(-1 * delta_seconds.total_seconds(),
                                          speech=False)
    else:
        total_time = (datetime.now(alert.timezone).timestamp() -
                      start_time.timestamp()) + \
                     delta_seconds.total_seconds()
        percent_remaining = delta_seconds.total_seconds() / total_time
        human_delta = nice_duration(delta_seconds.total_seconds(), speech=False)

    return {
        'alertId': alert.ident,
        'backgroundColor': '',  # TODO Color hex code
        'expired': alert.is_expired,
        'percentRemaining': percent_remaining,  # float percent remaining
        'timerName': alert.alert_name,
        'timeDelta': human_delta  # Human-readable time remaining
    }


def build_alarm_data(alert: Alert) -> dict:
    """
    Parse an alert object into a dict data structure for an alarm UI
    """
    if alert.alert_type != AlertType.ALARM:
        raise ValueError(f"Expected a timer, got: {alert.alert_type.name}")

    use_24h = use_24h_format()
    alarm_time = nice_time(
        datetime.fromisoformat(alert.data["next_expiration_time"]),
        speech=False, use_ampm=not use_24h, use_24hour=use_24h
    )
    if use_24h:
        alarm_time = alarm_time
        alarm_am_pm = ""
    else:
        alarm_time, alarm_am_pm = alarm_time.split()

    alarm_name = alert.alert_name.title() if alert.alert_name else "Alarm"

    alarm_expired = alert.is_expired
    alarm_index = alert.ident
    if alert.has_repeat:
        alarm_repeat_str = create_repeat_str(alert)
    else:
        alarm_repeat_str = translate("once").title()

    return {
        "alarmTime": alarm_time,
        "alarmAmPm": alarm_am_pm,
        "alarmName": alarm_name,
        "alarmExpired": alarm_expired,
        "alarmIndex": alarm_index,
        "alarmRepeat": alert.has_repeat,
        "alarmRepeatStr" : alarm_repeat_str
    }


def create_repeat_str(alert: Alert) -> str:

    def get_sequences(d):
        seq = [[d[0]]]
        for i in range(1, len(d)):
            if d[i-1]+1 == d[i]:
                seq[-1].append(d[i])
            else:
                seq.append([d[i]])
        return seq

    repeat_str = ""
    if alert.repeat_days:
        sequences = get_sequences(list(alert.repeat_days))
        for i, sequence in enumerate(sequences):
            first = get_abbreviation(min(sequence))
            last = get_abbreviation(max(sequence))
            if len(sequence) > 2:                
                sequences[i] = f"{first}-{last}"
            elif len(sequence) == 2:
                sequences[i] = f"{first},{last}"
            else:
                sequences[i] = f"{first}"
        repeat_str = ",".join(sequences)
    elif alert.repeat_frequency:
        repeat_str = nice_duration(alert.repeat_frequency.total_seconds(),
                                   speech=False)

    if alert.until:
        if repeat_str:
            repeat_str += "|"    
        repeat_str += f"{translate('until')} {datetime_display(alert.until.date())}"
            
    return repeat_str
