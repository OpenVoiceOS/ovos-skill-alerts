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

import datetime as dt
from time import time
from typing import Optional, List, Union, Tuple, Any
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from ovos_bus_client.message import Message, dig_for_message
from ovos_bus_client.util import get_message_lang
from ovos_config.locale import get_default_lang, get_default_tz
from ovos_date_parser import nice_time, nice_day, extract_datetime, extract_duration
from ovos_number_parser import extract_number
from ovos_skill_alerts.util import AlertPriority, Weekdays, AlertType, DAVType, LOCAL_USER
from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.config import use_24h_format, find_resource_file, get_date_format
from ovos_skill_alerts.util.locale import (
    voc_match,
    spoken_alert_type,
    get_words_list,
    spoken_duration,
    get_alert_type
)
from ovos_utils.log import LOG
from ovos_utterance_normalizer import UtteranceNormalizerPlugin
from rapidfuzz import fuzz


class Tokens(list):
    def __init__(self, chunks: list, message: Message = None):
        super().__init__(chunks)
        self.original: list = self[:]
        self.original_str: str = " ".join(self.original)
        self.message = message
        self.time_stripped = False
        self.extracted_time: Union[dt.datetime, dt.timedelta] = None

    @property
    def lang(self):
        return get_message_lang(self.message)

    def unmatched(self, original=False):
        if original:
            list_ = self.original
        else:
            list_ = self
        return [chunk for chunk in list_ if
                not (self.is_matched(chunk) or
                     chunk in get_words_list("noise_words.voc", self.lang))]

    def is_matched(self, chunk):
        return any([tag["match"] == chunk
                    for tag in self.message.data["__tags__"]])

    def strip_time(self):
        if self.time_stripped:
            return

        time_data = []
        lang = get_message_lang(self.message)
        for i, token in enumerate(self):
            if self.is_matched(token):
                continue
            time_ = None
            try:
                time_, remainder = extract_duration(token, lang=lang)
            except TypeError:
                pass
            if time_ is None:
                try:
                    extracted_content = extract_datetime(token, lang=lang)
                    if not extracted_content:
                        continue
                    time_, remainder = extracted_content
                except TypeError:
                    pass
            if time_:
                time_data.append(time_)
            self[i] = remainder

        self.extracted_time = time_data[0] if time_data else None

    def clear(self):
        self[:] = self.original
        self.time_stripped = False

        return self


def tokenize_utterance(message: Message) -> Tokens:
    """
    Get utterance tokens, split on matched vocab
    :param message: Message associated with intent match
    :returns: list of utterance tokens where a tag defines a token
    """
    utterance: str = message.data.get("utterance", "").lower()
    lang = get_message_lang(message)
    if utterance is None:
        return Tokens([], message)

    tags = message.data.get("__tags__")
    if tags is None:
        message.data["__tags__"] = []
        chunks = [utterance]
    else:
        tags.sort(key=lambda tag: tag["start_token"])
        extracted_words = [tag.get("match") for tag in tags]
        chunks = list()
        for word in extracted_words:
            parsed, utterance = utterance.split(word, 1)
            # strip possible connectors left behind due to split
            parsed = parsed.strip("-")
            chunks.extend((parsed, word))
        chunks.append(utterance)
    normalizer = UtteranceNormalizerPlugin.get_normalizer(lang=lang)
    tokens = Tokens([normalizer.normalize(chunk).lower()
                     for chunk in chunks if chunk.strip()], message)
    return tokens


def round_nearest_minute(alert_time: dt.datetime,
                         cutoff: dt.timedelta = dt.timedelta(minutes=10)) -> \
        dt.datetime:
    """
    Round an alert time to the nearest minute if it is longer than the cutoff
    :param alert_time: requested alert datetime
    :param cutoff: minimum delta to consider rounding the alert time
    :returns: datetime rounded to the nearest minute if delta exceeds cutoff
    """
    if alert_time <= dt.datetime.now(alert_time.tzinfo) + cutoff:
        return alert_time
    else:
        new_alert_time = alert_time.replace(second=0).replace(microsecond=0)
    return new_alert_time


def get_default_alert_name(alert_time: Union[dt.date, dt.datetime, dt.timedelta],
                           alert_type: AlertType,
                           timezone: dt.tzinfo = None,
                           now_time: Optional[dt.datetime] = None,
                           lang: str = None) -> \
        Optional[str]:
    """
    Build a default name for the specified alert
    :param alert_time: datetime of next alert expiration
    :param alert_type: AlertType of alert to name
    :param now_time: datetime to anchor timers for duration
    :param lang: Language to format response in
    :return: name for alert
    """
    if alert_time is None:
        return spoken_alert_type(alert_type, lang)

    timezone = timezone or alert_time.tzinfo if \
        isinstance(alert_time, dt.datetime) else get_default_tz()
    now_time = now_time or dt.datetime.now(tz=timezone)
    lang = lang or get_default_lang()
    if alert_type == AlertType.TIMER:
        time_str = spoken_duration(alert_time, now_time, lang)
    # TODO ordinalize (LF)
    elif alert_time.__class__ == dt.date:
        time_str = nice_day(alert_time, date_format=get_date_format(), lang=lang)
    else:
        use_24hr = use_24h_format()
        if isinstance(alert_time, dt.timedelta):
            alert_time += now_time
        time_str = nice_time(alert_time, lang=lang, speech=False, use_24hour=use_24hr, use_ampm=not use_24hr)
    return f"{time_str} {spoken_alert_type(alert_type, lang)}"


def has_default_name(alert: Alert, lang: str = None) -> bool:
    """
    Check if the alert name is a default name (ie not specifically named)
    :param alert_name: name of alert to check
    :param lang: language to format response in
    :return: True if alert_name is the default name for the alert
    """
    lang = lang or alert.lang
    expiration = alert.expiration.date() if alert.is_all_day else alert.expiration
    default_name = get_default_alert_name(expiration,
                                          alert.alert_type,
                                          alert.timezone,
                                          alert.created,
                                          lang)
    return alert.alert_name == default_name


def build_alert_from_intent(message: Message) -> Optional[Alert]:
    """
    Parses alert parameters from an intent message and constructs an Alert object.
    
    Extracts relevant alert information such as context, timezone, anchor time, tokens, alert type, repeat schedule, priority, alert time, end condition, audio file, and alert name from the provided message. Handles special cases for timers and all-day alerts. Returns an Alert instance if all required parameters are present, or None otherwise.
    
    Args:
        message: The message containing the intent and alert details.
    
    Returns:
        An Alert object constructed from the parsed parameters, or None if required parameters are missing.
    """
    lang = get_message_lang(message)
    LOG.debug(f"{lang}, {type(lang)}")

    data = dict()
    data["context"] = parse_alert_context_from_message(message)

    timezone = get_default_tz()
    timestamp = data.get("context").get("created")
    anchor_time = dt.datetime.fromtimestamp(timestamp).astimezone(timezone)

    tokens = tokenize_utterance(message)
    alert_type = get_alert_type(message)

    repeat = parse_repeat_from_message(message, tokens)
    if isinstance(repeat, dt.timedelta):
        repeat_interval = repeat
        repeat_days = None
    else:
        repeat_days = repeat
        repeat_interval = None

    # Parse data in a specific order since tokens are mutated in parse methods
    data["priority"] = parse_alert_priority_from_message(message, tokens)
    alert_time = parse_alert_time_from_message(message, tokens, timezone, anchor_time)
    until = parse_end_condition_from_message(message, tokens, timezone, alert_time or anchor_time)
    data["audio_file"] = parse_audio_file_from_message(message, tokens)

    if isinstance(until, (dt.timedelta, relativedelta,)):
        until = (alert_time or anchor_time) + until

    if alert_type == AlertType.TIMER and alert_time is None:
        # stopwatch timer
        alert_time = anchor_time
        data["context"]["stopwatch_mode"] = True
    elif alert_time is None:
        if repeat_interval:
            alert_time = anchor_time + repeat_interval
        elif until:
            alert_time = until

    if ((message.data.get("all_day") or voc_match(message.data["utterance"], "all_day", lang=lang))
            and alert_time is not None):
        alert_time = alert_time.date()

    data["expiration"] = alert_time
    data["until"] = until
    data["repeat_frequency"] = repeat_interval
    data["repeat_days"] = repeat_days

    data["alert_name"] = parse_alert_name_from_message(message, tokens) \
                         or get_default_alert_name(alert_time,
                                                   get_alert_type(message),
                                                   timezone,
                                                   now_time=anchor_time,
                                                   lang=lang)
    data["alert_type"] = alert_type
    if alert_type == AlertType.TODO:
        data["dav_type"] = DAVType.VTODO
    data["lang"] = lang
    return Alert.create(**data)


def parse_repeat_from_message(message: Message,
                              tokens: Optional[list] = None) -> Union[List[Weekdays], dt.timedelta]:
    """
    Parses the repeat schedule from a message, returning repeat weekdays or an interval.
      
    If the message or utterance indicates "everyday", "weekends", or "weekdays", returns the corresponding list of `Weekdays`. If a repeat interval or specific days are provided, parses and returns either a list of `Weekdays` or a `timedelta` representing the repeat interval. Removes handled tokens from the provided token list if applicable.
     
    Args:
        message: The message containing the utterance and intent data.
        tokens: Optional list of tokens to update as repeat information is parsed.
    
    Returns:
        A list of `Weekdays` if repeating on specific days, or a `timedelta` if repeating at a fixed interval.
    """
    repeat_days = list()
    lang = get_message_lang(message)
    # NOTE: voc_match is used in case intent was invoked without using adapt
    utt = message.data.get("utterance", "")
    if message.data.get("everyday") or voc_match(utt, "everyday", lang=lang):
        repeat_days = [Weekdays(i) for i in range(0, 7)]
    elif message.data.get("weekends") or voc_match(utt, "weekends", lang=lang):
        repeat_days = [Weekdays(i) for i in (5, 6)]
    elif message.data.get("weekdays") or voc_match(utt, "weekdays", lang=lang):
        repeat_days = [Weekdays(i) for i in range(0, 5)]
    elif message.data.get("repeat"):
        tokens = tokens or tokenize_utterance(message)
        repeat_index = tokens.index(message.data["repeat"]) + 1
        if repeat_index > len(tokens) - 1:
            return []

        repeat_clause = tokens.pop(repeat_index)
        repeat_days = list()
        remainder = ""
        zero_hour = dt.time()
        # Parse repeat days
        if voc_match(repeat_clause, "days", lang):
            for word in repeat_clause.split():  # Iterate over possible weekdays
                if word.isnumeric():
                    # Don't try to parse time intervals
                    remainder += f' {word}'
                    continue
                extracted_content = extract_datetime(word, lang=lang)
                if not extracted_content:
                    remainder += f' {word}'
                    continue
                extracted_dt = extracted_content[0]
                if extracted_dt.time() == zero_hour:
                    repeat_days.append(Weekdays(extracted_dt.weekday()))
                    remainder += '\n'
                else:
                    remainder += f' {word}'
            LOG.debug(("Parsed repeat days from message: "
                       f"{[d.name for d in repeat_days]}"))

        # Parse repeat interval
        if not repeat_days:
            extracted_duration = extract_duration(repeat_clause, lang=lang)
            if extracted_duration and not extracted_duration[0]:
                # Replace "the next week" with "1 week", etc.
                extracted_duration = extract_duration(f"1 {extracted_duration[1]}", lang=lang)
            if extracted_duration and extracted_duration[0]:
                duration, remainder = extracted_duration
                if remainder and remainder.strip():
                    tokens.insert(repeat_index, remainder.strip())
                LOG.debug("Parsed repeat frequency from message: {duration}")
                return duration

        if remainder:
            new_tokens = remainder.split('\n')
            for token in new_tokens:
                if token.strip():
                    tokens.insert(repeat_index, token.strip())
                    repeat_index += 1
    return repeat_days


def parse_end_condition_from_message(message: Message,
                                     tokens: Optional[list] = None,
                                     timezone: dt.tzinfo = None,
                                     anchor_time: dt.datetime = None) \
        -> Union[dt.datetime, dt.timedelta, None]:
    """
    Parses an end condition (such as "until" or "all day") from a message and optional tokens.
     
    If an "until" clause is present, extracts a datetime or duration for the end condition and updates the tokens accordingly. If an "all day" condition is detected, returns the end of the current day. Returns None if no end condition is found.
     
    Args:
        message: The message containing the utterance and intent data.
        tokens: Optional list of tokens parsed from the message.
        timezone: The timezone to use for datetime calculations.
        anchor_time: The reference datetime for relative parsing.
     
    Returns:
        A datetime or timedelta representing the end condition, or None if not found.
    """
    lang = get_message_lang(message)

    tokens = tokens or tokenize_utterance(message)
    timezone = timezone or get_default_tz()
    anchor_date = anchor_time or dt.datetime.now(timezone)
    if message.data.get("until"):
        idx = tokens.index(message.data["until"]) + 1
        if idx > len(tokens) - 1:
            return None
        end_clause = tokens.pop(idx)

        extracted_duration = extract_duration(end_clause, lang=lang)
        # extract duration first because of overlaps
        if extracted_duration and not extracted_duration[0]:
            # Replace "the next week" with "1 week", etc.
            extracted_duration = extract_duration(f"1 {extracted_duration[1]}", lang=lang)
        if extracted_duration and extracted_duration[0]:
            end_time, remainder = extracted_duration
        else:
            extracted_dt = extract_datetime(end_clause, anchorDate=anchor_date, lang=lang)
            if extracted_dt is None:
                end_time = extracted_dt
                remainder = end_clause
            else:
                end_time, remainder = extracted_dt
        tokens.insert(idx, remainder)

        LOG.debug(f"Parsed end time from message: {end_time}")
        return end_time
    elif message.data.get("all_day") or voc_match(message.data.get("utterance", ""), "all_day", lang=lang):
        return anchor_date.replace(hour=23, minute=59, second=59)

    return None


def parse_alert_time_from_message(message: Message,
                                  tokens: Tokens = None,
                                  timezone: dt.tzinfo = None,
                                  anchor_time: dt.datetime = None) -> \
        Optional[dt.datetime]:
    """
    Parse a requested alert time from the request utterance
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :param timezone: timezone of request, defaults to mycroft location
    :param anchor_time: The base datetime the utterance is relative to
    :returns: Parsed datetime for the alert or None if no time is extracted
    """
    lang = get_message_lang(message)

    timezone = timezone or get_default_tz()
    tokens = tokens or tokenize_utterance(message)
    anchor_time = anchor_time or dt.datetime.now(timezone)

    # ensure correct tzinfo (dt.timezone(dt.timedelta))
    # TODO Test if this is only relevat for unittests
    # tz = anchor_time.tzinfo.utcoffset(anchor_time)
    # anchor_time = anchor_time.replace(tzinfo=dt.timezone(tz))

    alert_time = None
    for token in tokens.unmatched():
        LOG.debug(f"Trying to parse time from token: {token}")
        extracted = extract_duration(token, lang=lang)
        if extracted and extracted[0]:
            duration, remainder = extracted
            alert_time = anchor_time + duration
            tokens[tokens.index(token)] = remainder
            break
        extracted = extract_datetime(token, anchorDate=anchor_time, lang=lang)
        if extracted and extracted[0]:
            alert_time, remainder = extracted
            tokens[tokens.index(token)] = remainder
            break
    LOG.debug(f"Parsed alert time from message: {alert_time}")
    # mark the tokens as time stripped
    tokens.extracted_time = alert_time
    tokens.time_stripped = True
    return alert_time


def parse_timedelta_from_message(message: Message,
                                 tokens: Tokens = None,
                                 timezone: dt.tzinfo = None,
                                 anchor_time: dt.datetime = None) -> \
        Optional[dt.timedelta]:
    """
    Parse the timedelta relative to the anchortime from the request utterance
    :param message: Message associated with intent match
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :param timezone: timezone of request, defaults to mycroft location
    :param anchor_time: The base datetime the utterance is relative to
    :returns: Parsed datetime for the alert or None if no time is extracted
    """
    timezone = timezone or get_default_tz()
    anchor_time = anchor_time or dt.datetime.now(timezone)

    alert_time = parse_alert_time_from_message(message, tokens,
                                               timezone, anchor_time)

    return alert_time - anchor_time if alert_time else None


# TODO: Toss - should be handled via OCP
def parse_audio_file_from_message(message: Message,
                                  tokens: Optional[list] = None) -> Optional[str]:
    """
    Parses the requested audio file name from the message, returning its file path if found.
  
    If the message indicates a playable alert, attempts to locate a resource file matching the alert name with supported audio extensions. Returns the file path if found, otherwise None.
    """
    tokens = tokens or tokenize_utterance(message)
    file = None
    if message.data.get("playable") or voc_match(message.data.get("utterance", ""), "playable"):
        name = parse_alert_name_from_message(message, tokens)
        file = find_resource_file(name, ("wav", "mp3", "ogg",))
    return file


def parse_alert_priority_from_message(message: Message,
                                      tokens: Optional[list] = None) -> AlertPriority:
    """
    Extracts the alert priority from a message or tokens.
  
    If a priority is specified in the message data or detected in the utterance, attempts to extract a numeric priority value from unmatched tokens. Returns the extracted priority if valid (1–10), otherwise returns the default average priority.
    """
    tokens = tokens or tokenize_utterance(message)
    lang = get_message_lang(message)

    priority = AlertPriority.AVERAGE.value
    if message.data.get("priority") or voc_match(message.data.get("utterance", ""), "priority", lang=lang):
        num = extract_number(" ".join(tokens.unmatched()), lang=lang)
        priority = num if num and num in range(1, 11) else priority
    return priority


def parse_alert_name_from_message(message: Message,
                                  tokens: Tokens = None,
                                  noise_words: List[str] = None) -> str:
    """
    Try to parse an alert name from unparsed tokens
    :param message: Message associated with the request
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :returns: Best guess at a name extracted from tokens
    """
    lang = get_message_lang(message)

    tokens = tokens or tokenize_utterance(message)
    tokens.strip_time()

    noise_words = noise_words or get_words_list("noise_words.voc", lang)
    candidate_names = list()
    # First try to parse a name from the remainder tokens
    for chunk in tokens.unmatched():
        cleaned_chunk = " ".join([word.lower() for word in chunk.split()
                                  if word not in noise_words])
        if cleaned_chunk:
            candidate_names.append(cleaned_chunk)
    # default name
    if not candidate_names:
        return ""

    LOG.info(f"Parsed possible names: {candidate_names}")
    return candidate_names[0]


def parse_alert_name_and_time_from_message(
        message: Message,
        tokens: list = None,
        timezone: dt.tzinfo = None,
        anchor_time: dt.datetime = None
) -> Tuple[Optional[str], Optional[dt.datetime]]:
    """
    Parse an alert name and time from a request
    :param message: Message associated with request
    :param tokens: optional tokens parsed from message by `tokenize_utterances`
    :param timezone: timezone of request, defaults to mycroft location
    :returns tuple containing alert name and alert time
    """
    tokens = tokens or tokenize_utterance(message)
    timezone = timezone or get_default_tz()
    return (
        parse_alert_time_from_message(message, tokens, timezone, anchor_time),
        parse_alert_name_from_message(message, tokens),
    )


def parse_alert_context_from_message(message: Message) -> dict:
    """
    Parse the request message context and ensure required parameters exist
    :param message: Message associated with the request
    :returns: dict context to include in Alert object
    """
    # TODO: what could the rest of message context be good for? {**message.context, **required_context}
    required_context = {
        "source": message.context.get("source") or ["skills"],
        "destination": message.context.get("destination") or "audio",
        # "session": message.context.get("session") or dict(),
        "user": message.context.get("user") or LOCAL_USER,
        "lang": get_message_lang(message),
        "ident": message.context.get("ident") or str(uuid4()),
        "origin_ident": message.context.get('ident'),
        "created": message.context.get("timing",
                                       {}).get("handle_utterance") or time()
    }
    return required_context


# TODO: no need for timezone in the signature
def extract_dt_or_duration(
        text: str, lang: str,
        anchor_time: dt.datetime = None,
        timezone: dt.tzinfo = None,
        add: bool = True
) -> Union[dt.datetime, dt.timedelta, None]:
    """
    Helper to extract either a duration or datetime
    If a duration is extracted and no anchor date is passed the timedelta will be
    returned else added/substracted to/from the anchor date
    :param text: the string to be parsed
    :param anchorDate: a datetime to which a timedelta is added to
    :param add: whether a duration should be added or substracted
    """
    lang = lang or get_default_lang()
    # timezone = timezone or get_default_tz()
    # if anchor_time:
    #     timezone = anchor_time.tzinfo
    # else:
    #     anchor_time = dt.datetime.now(timezone)

    time_, remainder = extract_duration(text, lang=lang)
    if time_ is None:
        # now = dt.datetime.now(timezone)
        time_, remainder = extract_datetime(text, anchorDate=anchor_time, lang=lang) or (None, text)
    if isinstance(time_, (dt.timedelta, relativedelta)):
        if anchor_time is not None:
            return anchor_time + time_ if add else anchor_time - time_, remainder
        else:
            return time_ if add else time_ * -1, remainder

    return time_, remainder


def parse_relative_time_from_message(message: Message,
                                     tokens: Optional[Tokens] = None,
                                     timezone: Optional[dt.tzinfo] = None,
                                     anchor_time: Optional[dt.datetime] = None):
    lang = get_message_lang(message)
    earlier = "earlier" in message.data

    timezone = timezone or get_default_tz()
    tokens = tokens or tokenize_utterance(message)

    for token in tokens.unmatched():
        time_, remainder = extract_dt_or_duration(token, lang,
                                                  anchor_time,
                                                  timezone,
                                                  not earlier)
        if time_:
            tokens[tokens.index(token)] = remainder
            return time_
    return None


def parse_timeframe_from_message(message: Message,
                                 tokens: Optional[Tokens] = None,
                                 timezone: Optional[dt.tzinfo] = None):
    """
    Parses a time frame with a start and optional end time from a message.
     
    If a conjunction like "and" is detected, attempts to extract an end time relative to the start. If the end time is midnight, adjusts it to cover the entire following day. If only a start time is found and it is at midnight, sets the end time to the end of that day.
     
    Args:
        message: The message containing the utterance to parse.
        tokens: Optional pre-tokenized representation of the utterance.
        timezone: Optional timezone information for interpreting times.
     
    Returns:
        A tuple (begin, end) where both are datetime objects or None if not found.
    """
    end = None
    tokens = tokens or tokenize_utterance(message)
    begin = parse_alert_time_from_message(message, tokens, timezone)

    if message.data.get("and") or voc_match(message.data.get("utterance", ""), "and"):
        end = parse_alert_time_from_message(message,
                                            tokens,
                                            timezone,
                                            anchor_time=begin)
        if end:
            # Set this to next day if 'end' is parsed as 00:00
            # queries about "today and tomorrow" should likely include
            # tomorrow
            if end.minute == 0 and end.hour == 0:
                end = end + dt.timedelta(days=1, seconds=-1)
    # if parsed time is 00:00 this is considerred a whole day check
    # eg "today", "tomorrow", "3rd of october", "tuesday"
    if end is None and begin and begin.minute == 0 and begin.hour == 0:
        end = begin + dt.timedelta(days=1, seconds=-1)

    return begin, end


def validate_dt_or_delta(response: str) -> Union[dt.datetime, dt.timedelta, str]:
    """
    Validates if the sentence contains a datetime or duration
    """
    message = dig_for_message()  # used inside get_response
    lang = get_message_lang(message) if message else get_default_lang()
    if voc_match(response, "no", lang):
        return "no"
    else:
        return extract_dt_or_duration(response, lang=lang)[0]


def validate_dt(response: str) -> Union[dt.datetime, str]:
    """
    Validates if the sentence contains a datetime
    """
    message = dig_for_message()  # used inside get_response
    lang = get_message_lang(message) if message else get_default_lang()
    if voc_match(response, "no", lang):
        return "no"
    else:
        dt_ = extract_datetime(response, lang=lang)
        return dt_ if dt_ is None else dt_[0]


def validate_number(response: str) -> int:
    message = dig_for_message()  # used inside get_response
    lang = get_message_lang(message) if message else get_default_lang()
    num = extract_number(response, lang=lang)
    if num:
        return int(num)
    return False


def get_week_range(ref_date: dt.datetime) -> Tuple[dt.datetime, dt.datetime]:
    """
    Get the start and end dates of the week containing the given reference date.

    Args:
        ref_date (datetime): The reference date to use for calculating the week
                             range.

    Returns:
        Tuple[datetime, datetime]: A tuple of datetime objects representing the
                                   start and end dates of the week containing the
                                   given reference date.
    """
    start = ref_date - dt.timedelta(days=ref_date.weekday())
    end = start + dt.timedelta(days=6)
    return start, end


def fuzzy_match(test: str, against: str, confidence: int = None) -> Any:
    """
    Rapidfuzz matcher
    Compares with different mechanisms (ratio/partial ratio/token sort ratio)
    to account for potential STT misbehaviour
    If no confindence cut [0-100] is passed, it returns the aggegated confidence
    else it compares the aggegated confidence to the confidence cut
    :param test: the test string
    :param against: the string to test against
    :param conf: confidence cut (optional)
    """

    ratio = fuzz.ratio(test, against)
    partial_ratio = fuzz.partial_ratio(test, against)
    token_sort_ratio = fuzz.token_sort_ratio(test, against)
    best = max(ratio, partial_ratio, token_sort_ratio)
    # LOG.debug(f"Fuzzy Match value {best}")

    return best > confidence if confidence is not None else best


def fuzzy_match_alerts(test: List[Alert], against: str, confidence: int = None) \
        -> Optional[Alert]:
    """
    Fuzzy matches a list of Alerts and returns the best match (alert names are
    tested)
    If a confidence cut [0-100] is passed only those matched above are considerred
    :param test: the alert list to test
    :param against: the string to test against
    :param conf: confidence cut (optional)
    """
    result = []
    for alert in test:
        fuzzy_conf = fuzzy_match(alert.alert_name, against)
        if confidence and fuzzy_conf > confidence:
            result.append((alert, fuzzy_conf))
    if result:
        return sorted(result, key=lambda x: x[1])[-1][0]
    return None
