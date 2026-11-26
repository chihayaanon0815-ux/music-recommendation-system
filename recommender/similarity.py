"""Text and tag helpers shared by the v2 recommender (standard library only).

The v1 contract compared genre strings with exact equality (after stripping
spaces). The v2 algorithm needs a softer notion of "same genre", so this
module centralises normalisation and set similarity:

* ``fold``  - NFKC + strip + casefold, used as the comparison key.
* ``genre_labels`` - keep the original labels for display, drop blanks and
  case-insensitive duplicates.
* ``match`` - preference coverage: how many of the requested tags a song
  covers, together with the labels that actually matched.
"""

import unicodedata


def as_text(value):
    """Return the field as a string, mapping None to an empty string."""
    return "" if value is None else str(value)


def fold(value):
    """Return a comparison key: NFKC, trimmed, case-folded."""
    return unicodedata.normalize("NFKC", as_text(value)).strip().casefold()


def genre_labels(value):
    """Split a '|'-separated genre field, keeping display order."""
    labels = []
    seen = set()
    for part in as_text(value).split("|"):
        label = part.strip()
        if not label:
            continue
        key = fold(label)
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def label_keys(labels):
    """Return the folded key set of an iterable of labels."""
    return {fold(label) for label in labels if fold(label)}


def terms(preferences, key):
    """Read one preference list, tolerating a missing key or a bare string."""
    values = preferences.get(key)
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    selected = []
    seen = set()
    for item in values:
        text = as_text(item).strip()
        if not text:
            continue
        folded = fold(text)
        if folded in seen:
            continue
        seen.add(folded)
        selected.append(text)
    return selected


def match(preferred, song_labels):
    """Return (coverage, matched_labels) for a preference/song pair.

    ``coverage`` is matched / requested, so a song covering one of two
    requested genres scores 0.5 instead of 0. ``matched_labels`` keeps the
    song's own spelling, which is what the reason text shows.
    """
    keys = label_keys(preferred)
    if not keys:
        return 0.0, []
    matched = []
    seen = set()
    for label in song_labels:
        key = fold(label)
        if key in keys and key not in seen:
            seen.add(key)
            matched.append(label)
    return len(matched) / len(keys), matched


def jaccard(left, right):
    """Jaccard similarity of two label iterables in [0, 1]."""
    a = label_keys(left)
    b = label_keys(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
