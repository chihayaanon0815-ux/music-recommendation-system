from collections import Counter
from heapq import nsmallest

from recommender.track_content import is_recommendable_track


def labels(text):
    return {part.strip() for part in text.split('|') if part.strip()}


def profile(items):
    genres, artists = Counter(), Counter()
    for song in items:
        if not song['matched']:
            continue
        genres.update(labels(song['genres']))
        if song['artist']:
            artists[song['artist']] += 1
    return genres, artists


def recommend_playlist(catalog, seeds, limit):
    genres, artists = profile(
        song for song in seeds if is_recommendable_track(song['song_name'], song['genres'], song['song_id'])
    )
    excluded = {song['song_id'] for song in seeds}
    excluded_names = {(song['song_name'].casefold(), song['artist'].casefold()) for song in seeds}

    def scored_tracks():
        for song in catalog:
            if (song['song_id'] in excluded or
                    (song['song_name'].casefold(), song['artist'].casefold()) in excluded_names):
                continue
            shared = sorted(labels(song['genres']) & genres.keys())
            artist_count = artists[song['artist']]
            score = 3 * sum(genres[tag] for tag in shared) + 2 * artist_count
            if score and is_recommendable_track(song['song_name'], song['genres'], song['song_id']):
                reasons = [f'{tag}（原歌单 {genres[tag]} 首）' for tag in shared]
                if artist_count:
                    reasons.append(f'{song["artist"]}（原歌单 {artist_count} 首）')
                yield {**song, 'score': score, 'reason': '；'.join(reasons)}

    return nsmallest(limit, scored_tracks(), key=lambda track: (-track['score'], track['song_id']))
