import datetime as dt
import re
from langcodes import closest_match
import os
from os.path import join, dirname
from typing import Optional, List, Union, Tuple

from ovos_bus_client.message import Message
from ovos_bus_client.util import get_message_lang
from ovos_config.locale import get_default_lang
from ovos_date_parser import (
    nice_duration,
    nice_time,
    nice_date,
    nice_date_time
)
from ovos_skill_alerts.util import AlertType, Weekdays, WEEKDAYS, WEEKENDS, EVERYDAY
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.config import use_24h_format, get_date_format
from ovos_utils.bracket_expansion import expand_template
from ovos_workshop.skills.ovos import join_word_list


def datetime_display(begin: dt.datetime,
                     end: Optional[dt.datetime] = None,
                     lang: str = None) -> str:
    lang = lang or get_default_lang()
    use_24h = use_24h_format()
    date_format = get_date_format()

    display = date_display(begin, date_format) + " " + \
              time_display(begin, use_24h, lang=lang)
    if end and end.date() != begin.date():
        display += " - " + date_display(end, date_format) + " " + \
                   time_display(end, use_24h, lang=lang)
    elif end:
        display += " - " + time_display(end, use_24h, lang=lang)

    return display


def time_display(dt_obj: dt.datetime,
                 use_24h: bool = True,
                 lang: str = None) -> str:
    lang = lang or get_default_lang()
    return nice_time(dt_obj, lang=lang,
                     speech=False,
                     use_24hour=use_24h,
                     use_ampm=not use_24h)


def date_display(dt_obj: dt.datetime,
                 date_format: str = "MDY") -> str:
    if date_format == "MDY":
        display = dt_obj.strftime('%-m/%-d/%Y')
    elif date_format == "DMY":
        display = dt_obj.strftime("%-d/%-m/%Y")
    elif date_format == "YMD":
        display = dt_obj.strftime("%Y/%-m/%-d")
    else:
        raise ValueError(f"Invalid date format: {date_format}")
    return display


def translate(word, lang=None):
    lang = lang or get_default_lang()
    lang = lang.lower()
    file = find_resource(f"{word}.dialog", lang)
    if file:
        with open(file) as f:
            return f.read().split("\n")[0]
    raise FileNotFoundError


def spoken_alert_type(alert_type: AlertType, lang: str = None) -> str:
    """
    Get a translated string for the specified alert_type
    :param alert_type: AlertType to be spoken
    :returns: translated string representation of alert_type
    """
    lang = lang or get_default_lang()
    if alert_type == AlertType.ALARM:
        return translate("alarm", lang)
    elif alert_type == AlertType.TIMER:
        return translate("timer", lang)
    elif alert_type == AlertType.REMINDER:
        return translate("reminder", lang)
    elif alert_type == AlertType.EVENT:
        return translate("event", lang)
    elif alert_type == AlertType.TODO:
        return translate("todo")
    return translate("alert", lang)


def get_words_list(res_name, lang: str = None) -> List[str]:
    """
    Returns a list of localized words from a skill resource
    :param lang: the language of the resource
    :returns list of noise words
    """
    lang = lang or get_default_lang()
    file = find_resource(res_name, lang)
    if file:
        with open(file) as f:
            entries = f.read().split("\n")
            word_list = []
            for entry in entries:
                if not entry or entry.startswith("#"):
                    continue
                word_list.extend(expand_template(entry))
            return word_list
    return list()


def find_resource(res_name, lang=None):
    """
    Helper function to locate the skill ressource on the file system
    :param res_name: filename of the resource
    :returns Path object of the file location or None
    """

    base_dir = dirname(dirname(__file__))
    root_path = join(base_dir, "locale")

    lang = lang or get_default_lang()
    langs = os.listdir(root_path)
    closest, sore = closest_match(lang, langs, max_distance=10)
    if closest == "und":
        return None  # unsupported lang

    path = join(root_path, closest, res_name)
    if os.path.exists(path):
        return path

    return None  # missing translation


def spoken_duration(alert_time: Union[dt.timedelta, dt.datetime],
                    anchor_time: Optional[dt.datetime] = None,
                    lang=None) -> str:
    """
    Gets a speakable string representing time until alert_time
    :param alert_time: Datetime or timedelta to get duration until
    :param anchor_time: Datetime to count duration from
    :param lang: Language to format response in
    :return: speakable duration string
    """
    lang = lang or get_default_lang()
    if isinstance(alert_time, dt.datetime):
        anchor_time = anchor_time or \
                      dt.datetime.now(alert_time.tzinfo).replace(microsecond=0)
        remaining_time: dt.timedelta = alert_time - anchor_time
    else:
        remaining_time = alert_time

    # changing resolution
    # days
    if remaining_time > dt.timedelta(weeks=1):
        _seconds = (remaining_time.total_seconds() // (60 * 60 * 24)) * (60 * 60 * 24)
    # hours
    elif remaining_time > dt.timedelta(days=1):
        _seconds = (remaining_time.total_seconds() // (60 * 60)) * (60 * 60)
    # minutes
    elif remaining_time > dt.timedelta(hours=1):
        _seconds = remaining_time.total_seconds() // 60 * 60
    # seconds
    else:
        _seconds = remaining_time.total_seconds()

    return nice_duration(int(_seconds), lang=lang)


def get_abbreviation(wd: Weekdays, lang=None) -> str:
    if wd == Weekdays.MON:
        return translate("abbreviation_monday", lang=lang)
    elif wd == Weekdays.TUE:
        return translate("abbreviation_tuesday", lang=lang)
    elif wd == Weekdays.WED:
        return translate("abbreviation_wednesday", lang=lang)
    elif wd == Weekdays.THU:
        return translate("abbreviation_thursday", lang=lang)
    elif wd == Weekdays.FRI:
        return translate("abbreviation_friday", lang=lang)
    elif wd == Weekdays.SAT:
        return translate("abbreviation_saturday", lang=lang)
    elif wd == Weekdays.SUN:
        return translate("abbreviation_sunday", lang=lang)


def get_alert_type_from_intent(message: Message) \
        -> Tuple[AlertType, str]:
    """
    Parse the requested alert type based on intent vocab
    :param message: Message associated with intent match
    :returns: tuple of AlertType requested and spoken_type 
    """
    # NOTE: voc_match is used in case intent was invoked without using adapt
    utt = message.data.get("utterance", "")

    lang = get_message_lang(message)

    if message.data.get("alarm") or \
            message.data.get("wake") or \
            voc_match("alarm", utt) or \
            voc_match("wake", utt):
        return AlertType.ALARM, translate("alarm", lang)
    elif message.data.get('timer') or voc_match("timer", utt):
        return AlertType.TIMER, translate("timer", lang)
    elif message.data.get('event') or \
            voc_match(utt, "event", lang):
        return AlertType.EVENT, translate("event", lang)
    elif message.data.get('reminder') or \
            message.data.get('remind') or \
            voc_match("reminder", utt) or \
            voc_match("remind", utt):
        return AlertType.REMINDER, translate("reminder", lang)
    elif message.data.get('alert') or voc_match("alert", utt):
        return AlertType.ALL, translate("alert", lang)
    return AlertType.ALL, translate("alert", lang)


def get_alert_type(message: Message) -> AlertType:
    """
    Get the alert type enum from the intent passed 
    :param message: Message associated with request
    :returns: alert type enum
    """
    return get_alert_type_from_intent(message)[0]


def spoken_weekday(weekday: Weekdays, lang: str) -> str:
    """
    Get a translated string for the specified weekday
    :param weekday: Weekday to be spoken
    :returns: translated string representation of weekday
    """
    if weekday == Weekdays.MON:
        return translate("monday", lang)
    if weekday == Weekdays.TUE:
        return translate("tuesday", lang)
    if weekday == Weekdays.WED:
        return translate("wednesday", lang)
    if weekday == Weekdays.THU:
        return translate("thursday", lang)
    if weekday == Weekdays.FRI:
        return translate("friday", lang)
    if weekday == Weekdays.SAT:
        return translate("saturday", lang)
    if weekday == Weekdays.SUN:
        return translate("sunday", lang)


def get_alert_dialog_data(alert: Alert,
                          lang: str,
                          anchor_date: dt.datetime = None) -> dict:
    """
    Parse a dict of data to be passed to the dialog renderer for the alert.
    :param alert: Alert to build dialog for
    :param lang: User language to be spoken
    :returns: dict dialog_data to pass to `speak_dialog`
    """
    lang = lang or alert.lang
    use_24hour = use_24h_format()

    expired_time = alert.data["next_expiration_time"]
    expired_time = dt.datetime.fromisoformat(expired_time)
    spoken_type = spoken_alert_type(alert.alert_type, lang)
    default_name = spoken_type in alert.alert_name

    if anchor_date is None:
        anchor_date = dt.datetime.now(expired_time.tzinfo)
    # Check if expiration was some time today
    if anchor_date.date() != expired_time.date() and \
            not alert.has_repeat:
        if alert.is_all_day:
            spoken_time = f"{nice_date(expired_time, lang=lang)}, "
            spoken_time += translate("whole_day", lang)
        else:
            # noinspection PyTypeChecker
            spoken_time = nice_date_time(expired_time, lang=lang,
                                         use_24hour=use_24hour,
                                         use_ampm=not use_24hour)
    else:
        if alert.is_all_day:
            spoken_time = translate("whole_day", lang)
        else:
            # noinspection PyTypeChecker
            spoken_time = nice_time(expired_time, lang=lang,
                                    use_24hour=use_24hour,
                                    use_ampm=not use_24hour)

    # the name is set to an empty string if this is a default
    # the subsequent intent handler should decide how this is voiced
    data = {"begin": spoken_time,
            "whole_day": alert.is_all_day,
            "remaining": spoken_duration(expired_time,
                                         lang=lang),
            "name": "" if default_name else alert.alert_name,
            "kind": spoken_type}
    # add event end
    if alert.until and not alert.is_all_day:
        if anchor_date.date() != alert.until.date():
            spoken_time = nice_date_time(alert.until, lang=lang,
                                         use_24hour=use_24hour,
                                         use_ampm=not use_24hour)
        else:
            # noinspection PyTypeChecker
            spoken_time = nice_time(alert.until, lang=lang,
                                    use_24hour=use_24hour,
                                    use_ampm=not use_24hour)
        data["end"] = spoken_time

    if alert.repeat_days:
        if alert.repeat_days == WEEKDAYS:
            data["repeat"] = translate("weekday", lang)
        elif alert.repeat_days == WEEKENDS:
            data["repeat"] = translate("weekend", lang)
        elif alert.repeat_days == EVERYDAY:
            data["repeat"] = translate("day", lang)
        else:
            data["repeat"] = join_word_list([spoken_weekday(day, lang)
                                             for day in alert.repeat_days],
                                            connector="and", sep=",", lang=lang)
    elif alert.repeat_frequency:
        data["repeat"] = nice_duration(
            alert.repeat_frequency.total_seconds(), lang=lang)

    if alert.prenotification:
        data["prenotification"] = nice_time(alert.prenotification, lang=lang)

    return data


def voc_match(utterance: str,
              resource: str,
              lang: str = None,
              exact: bool = False) -> bool:
    """
    Compares a string against a given words list
    If exact the utterance must be identical, otherwise a part of the sentence
    """
    if not resource or not utterance:
        return False
    else:
        if not resource.endswith(".voc"):
            resource = f"{resource}.voc"
        words = get_words_list(resource, lang)
        if exact:
            return any(i.strip() == utterance.lower() for i in words)
        else:
            return any([re.match(r".*\b" + i + r"\b.*", utterance.lower()) for i in words])
