"""Identify explicit speech material for music recommendation."""

import re
import unicodedata

from recommender.reviewed_tracks import CONFIRMED_MUSIC_IDS, MIXED_TRACK_IDS, SPOKEN_TRACK_IDS


SPEECH_LABELS = {"朗读与访谈", "非音乐音频"}
SPEECH_TITLE = re.compile(
    r"^(?:track\s+)?(?:commentary|interview|spoken introduction)"
    r"(?:\s*[:：—–]|\s+-\s+)|"
    r"[\[(](?:track\s+)?(?:commentary|interview)(?:\s+\d+|\s+version)?[\])]\s*$|"
    r"\s[-—–]\s(?:track\s+commentary|interview\s+with)\b|"
    r"\binterviews?\s+(?:19|20)\d{2}\b|"
    r"^(?:曲目解说|歌曲解说|访谈|訪談|音轨讲解)\s*[:：]",
    re.IGNORECASE,
)


def is_recommendable_track(title, genres, song_id=""):
    if song_id in SPOKEN_TRACK_IDS or song_id in MIXED_TRACK_IDS:
        return False
    if song_id in CONFIRMED_MUSIC_IDS:
        return True
    labels = genres.split("|") if isinstance(genres, str) else genres
    return not (
        SPEECH_LABELS.intersection(label.strip() for label in labels if label)
        or SPEECH_TITLE.search(unicodedata.normalize("NFKC", title).strip())
    )
