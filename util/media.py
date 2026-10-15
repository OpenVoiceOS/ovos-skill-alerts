from typing import List 

from ovos_utils.log import LOG
from ovos_config import get_default_lang
from ovos_bus_client import Message, MessageBusClient
try:
    from ovos_plugin_common_play.ocp.status import MediaType
    from ovos_plugin_common_play.ocp.search import OCPQuery
    from ovos_plugin_common_play.ocp.media import (
        MediaEntry,
        PlaybackType
    )
    OCP_RUNNNING = True

except ImportError:
    OCP_RUNNNING = False
    pass

from ovos_skill_alerts.util.alert import Alert
from ovos_skill_alerts.util.locale import get_words_list, voc_match


LANG2MEDIA = {
    "audio": ["audio"],
    "music": ["music"],
    "video": ["video"],
    "audiobook": ["audiobook"],
    "podcast": ["podcast"],
    "radio": ["radio"],
    "news": ["news"]
}


def ocp_query(phrase: str, message: Message, bus: MessageBusClient) \
    -> List[dict]:
    """
    Checks if there are results found in the search and returns the
    best
    """
    result = None
    if not OCP_RUNNNING:
        return result

    type_str = get_ocp_media_type(message).upper()

    query = OCPQuery(phrase, media_type=MediaType[type_str], bus=bus)
    query.send()
    query.wait()
    
    if query.search_playlist:
        query.search_playlist.sort_by_conf()
        result = query.search_playlist[0]
        if isinstance(result, MediaEntry):
            result = result.as_dict
    
    return result


def ocp_request(alert: Alert, bus: MessageBusClient):
    if not OCP_RUNNNING:
        return None
    elif alert.media_type not in ("ocp", "file",):
        LOG.error(f"Wrong type for ocp request: {alert.media_type}")
        return None

    media = dict()
    if alert.media_type == "file":
        media["playback"] = PlaybackType.AUDIO
        media["uri"] = alert.audio_file
        media["titel"] = alert.alert_name
    elif alert.media_type == "ocp":  # change to "ocp_query"
        media = alert.ocp_request
    
    request_msg = Message("ovos.common_play.play", {"media": media})
    LOG.debug("started common play request")
    result = bus.wait_for_response(request_msg,
                                   "ovos.common_play.track_info.response",
                                   timeout=6)
    LOG.debug(f"OCP request success: {True if result is not None else False}")
    return result


def get_ocp_media_type(message: Message) -> str:
    lang = message.data.get("lang")
    _update_lang2media(lang)

    media_str = message.data.get("media") 
    for type_, tx in LANG2MEDIA.items():
        if media_str in tx:
            return type_
    
    return "generic"


def _update_lang2media(lang: str = ""):
    lang = lang or get_default_lang()

    for type_ in LANG2MEDIA.keys():
        LANG2MEDIA[type_] = get_words_list(f"{type_}.dialog", lang)


def get_media_source_from_intent(message: Message):
    if message.data.get("file"):
        return "file"
    elif message.data.get("ocp"):
        return "ocp"
    return None


def validate_ocp_response(response):
    if voc_match(response, "cancel"):
        return None
    
