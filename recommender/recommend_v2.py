"""Deterministic, explainable recommender, version 2.

Differences from the v1 contract, all of them additive and opt-in:

1. Soft genre matching   - a song covering k of n requested genres earns
   ``GENRE_WEIGHT * k / n`` instead of an all-or-nothing +3.
2. Popularity prior      - artist and genre frequency inside the catalogue
   adds a small, bounded bonus so that ties break towards titles a user can
   actually find, and the no-preference fallback becomes meaningful.
3. Diversity reranking   - Maximal Marginal Relevance over the candidate pool
   so the top-N does not fill up with one artist or one genre.
4. Explanation text      - each reason carries the numbers behind the score,
   e.g. ``风格匹配：流行（覆盖 1/2，+1.50）``.

Everything stays deterministic: no randomness, no training, ties always fall
back to ``song_id`` string order, and the input objects are never mutated.

Public API
----------
recommend_v2(songs, preferences, limit=10, *, diversity=0.3,
             popularity_weight=0.6, exclude_ids=None) -> list[dict]
recommend_from_seeds(catalog, seeds, limit=10, *, diversity=0.3,
                     popularity_weight=0.6) -> list[dict]
"""

import math

from .similarity import as_text, fold, genre_labels, jaccard, match, terms

GENRE_WEIGHT = 3.0
ARTIST_WEIGHT = 2.0
POPULARITY_WEIGHT = 0.6
ARTIST_PENALTY = 0.4
DEFAULT_DIVERSITY = 0.3

DEFAULT_REASON = (
    "默认推荐：未选择偏好，按曲库热度（歌手与风格出现频次）排序"
)
SEED_PREFIX = "来自原歌单："


def _check_parameters(limit, diversity):
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TypeError("limit must be an int")
    if not isinstance(diversity, (int, float)) or isinstance(diversity, bool):
        raise TypeError("diversity must be a number")
    if not 0 <= float(diversity) <= 1:
        raise ValueError("diversity must be within [0, 1]")


def _prepare(songs):
    """Copy the usable rows once, dropping blanks and duplicate ids."""
    items = []
    seen = set()
    for song in songs:
        song_id = as_text(song.get("song_id")).strip()
        song_name = as_text(song.get("song_name")).strip()
        if not song_id or not song_name or song_id in seen:
            continue
        seen.add(song_id)
        items.append({
            "song_id": song_id,
            "song_name": song_name,
            "artist": as_text(song.get("artist")).strip(),
            "genres_raw": as_text(song.get("genres")),
            "labels": genre_labels(song.get("genres")),
        })
    return items


def _stats(items):
    """Artist and genre frequency tables for the popularity prior."""
    artists = {}
    genres = {}
    for item in items:
        key = fold(item["artist"])
        if key:
            artists[key] = artists.get(key, 0) + 1
        for label in item["labels"]:
            gkey = fold(label)
            genres[gkey] = genres.get(gkey, 0) + 1
    return {
        "artists": artists,
        "genres": genres,
        "max_artist": max(artists.values(), default=0),
        "max_genre": max(genres.values(), default=0),
    }


def _popularity(item, stats):
    """Bounded popularity score in [0, 1]: 60% artist, 40% genre frequency."""
    max_artist = stats["max_artist"]
    max_genre = stats["max_genre"]
    if not max_artist and not max_genre:
        return 0.0
    artist_part = 0.0
    if max_artist:
        count = stats["artists"].get(fold(item["artist"]), 0)
        if count:
            artist_part = math.log1p(count) / math.log1p(max_artist)
    genre_part = 0.0
    if max_genre and item["labels"]:
        ratios = []
        for label in item["labels"]:
            count = stats["genres"].get(fold(label), 0)
            ratios.append(math.log1p(count) / math.log1p(max_genre) if count else 0.0)
        # Strongest tag instead of the average: a song with one niche tag and
        # one common tag should not look less popular than a common-tag-only
        # song, otherwise multi-tag tracks are systematically penalised.
        genre_part = max(ratios)
    # Genre breadth matters more than a single prolific artist, otherwise cold
    # start would just list the discography of whoever has the most tracks.
    return 0.4 * artist_part + 0.6 * genre_part


def _format_number(value):
    return f"{value:.2f}"


def _reason(matched_labels, coverage, requested, artist_hit, popularity):
    parts = []
    if matched_labels:
        text = f"风格匹配：{'、'.join(matched_labels)}"
        text += f"（覆盖 {len(matched_labels)}/{requested}，+{_format_number(GENRE_WEIGHT * coverage)}）"
        parts.append(text)
    if artist_hit:
        parts.append(f"歌手匹配：{artist_hit}（+{_format_number(ARTIST_WEIGHT)}）")
    if popularity >= 0.05:
        parts.append(f"曲库热度 +{_format_number(POPULARITY_WEIGHT * popularity)}")
    return "；".join(parts)


def _candidate_pool(candidates, size, max_per_artist):
    """Take the best ``size`` candidates while keeping several artists in play.

    Without this, a prolific artist (hundreds of tracks in one genre) fills the
    whole top-N before diversity reranking is even reached.
    """
    pool = []
    per_artist = {}
    quota = None if max_per_artist is None else max(2, max_per_artist * 4)
    for item in candidates:
        key = fold(item["artist"])
        if key and quota is not None and per_artist.get(key, 0) >= quota:
            continue
        per_artist[key] = per_artist.get(key, 0) + 1 if key else 0
        pool.append(item)
        if len(pool) >= size:
            break
    return pool


def _diversified(candidates, limit, diversity, max_per_artist=2):
    """Maximal Marginal Relevance reranking, deterministic tie-breaking.

    A single artist is capped at ``max_per_artist`` results; if that cap leaves
    too few candidates the cap is relaxed so the caller still gets ``limit``
    results when the catalogue is genuinely narrow.
    """
    if limit <= 0 or not candidates:
        return []
    pool = _candidate_pool(candidates, max(limit * 6, 120), max_per_artist)
    top = max(item["score"] for item in pool) or 1.0
    selected = []
    artist_used = {}
    relaxed = False
    while pool and len(selected) < limit:
        best_key = None
        best_item = None
        for item in pool:
            artist_key = fold(item["artist"])
            if (artist_key and max_per_artist is not None and not relaxed
                    and artist_used.get(artist_key, 0) >= max_per_artist):
                continue
            relevance = item["score"] / top
            penalty = 0.0
            for chosen in selected:
                overlap = jaccard(item["labels"], chosen["labels"])
                same_artist = bool(item["artist"]) and fold(item["artist"]) == fold(chosen["artist"])
                candidate_penalty = overlap + (ARTIST_PENALTY if same_artist else 0.0)
                penalty = max(penalty, min(1.0, candidate_penalty))
            key = (-(relevance - diversity * penalty), item["song_id"])
            if best_key is None or key < best_key:
                best_key = key
                best_item = item
        if best_item is None:
            if relaxed:
                break
            relaxed = True
            continue
        selected.append(best_item)
        artist_key = fold(best_item["artist"])
        if artist_key:
            artist_used[artist_key] = artist_used.get(artist_key, 0) + 1
        pool.remove(best_item)
    return selected


def _output(item, score, reason):
    return {
        "song_id": item["song_id"],
        "song_name": item["song_name"],
        "artist": item["artist"],
        "genres": item["genres_raw"],
        "score": round(score, 2),
        "reason": reason,
    }


def _default_results(items, stats, limit):
    ranked = sorted(
        items,
        key=lambda item: (-_popularity(item, stats), item["song_id"]),
    )
    return [
        _output(item, 0.0, DEFAULT_REASON)
        for item in ranked[:limit]
    ]


def build_index(songs):
    """Normalise the catalogue once and reuse it for many queries.

    A web page can call this at start-up and pass ``index`` to every request:
    building the index is O(N), while the per-query scoring/sorting stays
    O(N log N) without repeating normalisation and frequency counts.
    """
    items = _prepare(songs)
    return {"items": items, "stats": _stats(items)}


def recommend_v2(songs, preferences, limit=10, *, diversity=DEFAULT_DIVERSITY,
                 popularity_weight=POPULARITY_WEIGHT, exclude_ids=None,
                 max_per_artist=2, index=None):
    """Rank songs for explicit genre/artist preferences (version 2).

    See the module docstring for the differences against contract v1.
    ``exclude_ids`` lets the caller drop already-heard tracks; ``index`` is an
    optional result of ``build_index``.
    """
    if preferences is None:
        preferences = {}
    if not isinstance(preferences, dict):
        raise TypeError("preferences must be a dict")
    if limit is None:
        limit = 10
    _check_parameters(limit, diversity)
    if limit <= 0:
        return []

    requested_genres = terms(preferences, "genres")
    requested_artists = terms(preferences, "artists")
    artist_keys = {fold(artist) for artist in requested_artists}
    excluded = {as_text(x).strip() for x in (exclude_ids or []) if as_text(x).strip()}

    index = index or build_index(songs)
    items = [item for item in index["items"] if item["song_id"] not in excluded]
    stats = index["stats"]
    has_preferences = bool(requested_genres or requested_artists)

    if not has_preferences:
        return _default_results(items, stats, limit)

    candidates = []
    for item in items:
        coverage, matched_labels = match(requested_genres, item["labels"])
        artist_hit = item["artist"] if item["artist"] and fold(item["artist"]) in artist_keys else ""
        if coverage <= 0 and not artist_hit:
            continue
        popularity = _popularity(item, stats)
        score = (GENRE_WEIGHT * coverage
                 + (ARTIST_WEIGHT if artist_hit else 0.0)
                 + popularity_weight * popularity)
        candidates.append({
            **item,
            "score": score,
            "reason": _reason(
                matched_labels, coverage, len(requested_genres),
                artist_hit, popularity,
            ),
        })

    if not candidates:
        return []
    candidates.sort(key=lambda item: (-item["score"], item["song_id"]))
    chosen = _diversified(candidates, limit, float(diversity), max_per_artist)
    return [_output(item, item["score"], item["reason"]) for item in chosen]


def recommend_from_seeds(catalog, seeds, limit=10, *, diversity=DEFAULT_DIVERSITY,
                         popularity_weight=POPULARITY_WEIGHT, exclude_ids=None,
                         max_per_artist=None, index=None):
    """Recommend follow-up tracks from a playlist's own songs (version 2).

    Each seed contributes its genres and artist to a weighted profile:
    a genre present in every seed earns the full ``GENRE_WEIGHT``, one that
    appears in a single seed earns a fraction. Seeds themselves are removed
    from the candidate pool, exactly like the v1 playlist helper.
    """
    if limit is None:
        limit = 10
    _check_parameters(limit, diversity)
    if limit <= 0:
        return []

    seed_items = _prepare(seeds)
    if not seed_items:
        return []

    genre_counts = {}
    artist_counts = {}
    for item in seed_items:
        for label in item["labels"]:
            key = fold(label)
            genre_counts[key] = genre_counts.get(key, 0) + 1
        key = fold(item["artist"])
        if key:
            artist_counts[key] = artist_counts.get(key, 0) + 1
    max_genre = max(genre_counts.values(), default=0) or 1
    max_artist = max(artist_counts.values(), default=0) or 1

    excluded = {item["song_id"] for item in seed_items}
    excluded_names = {
        (fold(item["song_name"]), fold(item["artist"])) for item in seed_items
    }
    excluded |= {as_text(x).strip() for x in (exclude_ids or []) if as_text(x).strip()}

    index = index or build_index(catalog)
    items = [
        item for item in index["items"]
        if item["song_id"] not in excluded
        and (fold(item["song_name"]), fold(item["artist"])) not in excluded_names
    ]
    stats = index["stats"]

    candidates = []
    for item in items:
        parts = []
        score = 0.0
        matched = []
        for label in item["labels"]:
            key = fold(label)
            count = genre_counts.get(key, 0)
            if count:
                matched.append((label, count))
                score += GENRE_WEIGHT * (count / max_genre)
                parts.append(f"{label}（原歌单 {count} 首）")
        artist_count = artist_counts.get(fold(item["artist"]), 0)
        if artist_count:
            # Keep artist continuity strong (a playlist seeded with 8 tracks of
            # one artist should keep offering that artist), but cap the bonus at
            # three tracks so a single seed cannot swamp the genre signal.
            score += ARTIST_WEIGHT * min(artist_count, 3)
            parts.append(f"{item['artist']}（原歌单 {artist_count} 首）")
        if score <= 0:
            continue
        popularity = _popularity(item, stats)
        score += popularity_weight * popularity
        candidates.append({
            **item,
            "score": score,
            "reason": SEED_PREFIX + "；".join(parts) + f"（+{_format_number(score)}）",
        })

    if not candidates:
        return []
    candidates.sort(key=lambda item: (-item["score"], item["song_id"]))
    chosen = _diversified(candidates, limit, float(diversity), max_per_artist)
    return [_output(item, item["score"], item["reason"]) for item in chosen]
