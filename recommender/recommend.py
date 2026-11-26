"""Deterministic, explainable genre/artist recommender (contract v1).

Public API
----------
recommend(songs, preferences, limit=10) -> list[dict]

The module only uses the Python standard library so that it can be imported
by the offline Flask page and packaged for a Windows machine without Python
or Java. See docs/recommendation/algorithm_spec.md for the full specification.
"""

from recommender.track_content import is_recommendable_track

DEFAULT_LIMIT = 10
GENRE_WEIGHT = 3
ARTIST_WEIGHT = 2

DEFAULT_REASON = "默认推荐：未选择偏好，按 song_id 字典序展示"


def _text(value):
    """Return the field as a string, mapping None to an empty string."""
    return "" if value is None else str(value)


def _split_genres(value):
    """Split a '|'-separated genre field, dropping blanks and duplicates."""
    genres = []
    seen = set()
    for item in _text(value).split("|"):
        genre = item.strip()
        if genre and genre not in seen:
            seen.add(genre)
            genres.append(genre)
    return genres


def _selection(preferences, key):
    """Read one preference list, tolerating a missing key or a bare string."""
    values = preferences.get(key)
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    selected = []
    seen = set()
    for item in values:
        value = _text(item).strip()
        if value and value not in seen:
            seen.add(value)
            selected.append(value)
    return selected


def _build_reason(matched_genres, artist_matched):
    parts = []
    if matched_genres:
        parts.append("风格匹配：" + "、".join(matched_genres))
    if artist_matched:
        parts.append("歌手匹配：" + artist_matched)
    return "；".join(parts)


def recommend(songs, preferences, limit=DEFAULT_LIMIT):
    """Rank songs against the user's genre and artist preferences.

    Parameters
    ----------
    songs : list[dict]
        Records with song_id, song_name, artist, genres (genres is a
        '|'-separated string).
    preferences : dict
        {"genres": [...], "artists": [...]}; missing keys mean no selection.
    limit : int
        Maximum number of results. A non-positive limit returns [].

    Returns
    -------
    list[dict]
        New dictionaries with song_id, song_name, artist, genres, score and
        a non-empty reason. Input objects are never modified.
    """
    if preferences is None:
        preferences = {}
    if not isinstance(preferences, dict):
        raise TypeError("preferences must be a dict")
    if limit is None:
        limit = DEFAULT_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TypeError("limit must be an int")
    if limit <= 0:
        return []

    selected_genres = _selection(preferences, "genres")
    selected_artists = _selection(preferences, "artists")
    has_preferences = bool(selected_genres or selected_artists)

    results = []
    seen_ids = set()
    for song in songs:
        song_id = _text(song.get("song_id")).strip()
        song_name = _text(song.get("song_name")).strip()
        if not song_id or not song_name:
            continue
        if song_id in seen_ids:
            continue
        seen_ids.add(song_id)

        song_genres = _split_genres(song.get("genres"))
        artist = _text(song.get("artist")).strip()

        matched = sorted(g for g in song_genres if g in selected_genres)
        artist_matched = artist if artist and artist in selected_artists else ""

        score = GENRE_WEIGHT * len(matched) + (ARTIST_WEIGHT if artist_matched else 0)

        if has_preferences:
            if score <= 0:
                continue
            reason = _build_reason(matched, artist_matched)
        else:
            score = 0
            reason = DEFAULT_REASON

        if not is_recommendable_track(song_name, song_genres, song_id):
            continue

        results.append({
            "song_id": _text(song.get("song_id")),
            "song_name": _text(song.get("song_name")),
            "artist": _text(song.get("artist")),
            "genres": _text(song.get("genres")),
            "score": score,
            "reason": reason,
        })

    results.sort(key=lambda item: (-item["score"], item["song_id"]))
    return results[:limit]
