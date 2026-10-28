"""The OCP media type get_ocp_media_type reads from an alarm request.

The intents put the media the user named in the ``{mediakind}`` slot, and
get_ocp_media_type read ``data["media"]``, which no intent fills, so every
request was "generic". It reads ``mediakind`` now, against a media_<type>.voc
per locale, through ovos-spec-tools' matcher: case and accents do not count.
"""
import pytest
from ovos_bus_client.message import Message

from ovos_skill_alerts.util.media import get_ocp_media_type


def _media_type(lang, **data):
    return get_ocp_media_type(Message("create_alarm.intent",
                                      {"lang": lang, **data}, {"lang": lang}))


@pytest.mark.parametrize("lang, spoken, expected", [
    ("en-US", "music", "music"),
    ("en-US", "Podcasts", "podcast"),
    ("en-US", "the news", "news"),
    ("de-DE", "Hörbücher", "audiobook"),
    ("de-DE", "horbuch", "audiobook"),
    ("pt-PT", "Livro de áudio", "audiobook"),
    ("pt-PT", "audio", "audio"),
    ("pt-BR", "Rádio", "radio"),
    ("es-ES", "MÚSICA", "music"),
    ("fr-FR", "vidéo", "video"),
    ("ru-RU", "Подкасты", "podcast"),
    ("fa-IR", "آهنگ", "music"),
])
def test_the_mediakind_slot_names_the_media_type(lang, spoken, expected):
    assert _media_type(lang, mediakind=spoken) == expected


def test_the_older_media_key_still_reads():
    assert _media_type("en-US", media="radio") == "radio"


@pytest.mark.parametrize("data", [{}, {"mediakind": "a lullaby"}])
def test_nothing_known_is_generic(data):
    assert _media_type("en-US", **data) == "generic"


def test_every_locale_ships_a_vocabulary_for_each_media_type():
    import os
    from ovos_skill_alerts.util.media import MEDIA_TYPES
    root = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "locale")
    missing = [f"{lang}/vocab/media_{t}.voc" for lang in sorted(os.listdir(root))
               for t in MEDIA_TYPES
               if not os.path.isfile(os.path.join(root, lang, "vocab",
                                                  f"media_{t}.voc"))]
    assert missing == []
