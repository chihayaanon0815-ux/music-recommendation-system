"""Validate the locally supplied reviewed catalog against its release manifest."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        yield from csv.DictReader(handle)


def verify(folder, manifest):
    for name, expected in manifest['files'].items():
        path = folder/name
        if path.stat().st_size != expected['bytes']:
            raise ValueError(f'Unexpected file size: {name}')
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected['sha256']:
                raise ValueError(f'Unexpected file checksum: {name}')
    seen, counts = set(), Counter()
    fields = ['song_id', 'song_name', 'artist', 'genres']
    with (folder/'songs.csv').open(encoding='utf-8-sig', newline='') as handle:
        songs = csv.DictReader(handle)
        if songs.fieldnames != fields:
            raise ValueError('Invalid songs.csv header')
        for song in songs:
            sid = song['song_id']
            if not sid or sid in seen or not song['song_name'] or not song['genres']:
                raise ValueError(f'Invalid or duplicate song: {sid}')
            seen.add(sid)
            counts.update(set(song['genres'].split('|')))
    if len(seen) != manifest['songs']:
        raise ValueError('Unexpected number of songs')
    if dict(counts) != {r['genre']:int(r['count']) for r in rows(folder/'genre_counts.csv')}:
        raise ValueError('genre_counts.csv does not match songs.csv')
    for name in ('genre_conflict_review.csv','duplicate_review.csv','genre_ranking_policy.csv'):
        if any(r['song_id'] not in seen for r in rows(folder/name)):
            raise ValueError(f'Unknown song ID in {name}')
    return len(seen)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('catalog_dir', type=Path)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest or Path(__file__).with_name('manifest.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    print(f'OK: {verify(args.catalog_dir, manifest):,} tracks')
