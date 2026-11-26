import csv
import json
from collections import Counter
from pathlib import Path

from catalog import export, key, names_for, song_title, write_csv

root = Path(__file__).resolve().parents[2]
state = root / 'work/catalog_run/progress.json'
out = root / 'outputs/多来源采集-本轮结果'
states = json.loads(state.read_text(encoding='utf-8'))
count = export(out, states)
with (out / 'songs_candidates.csv').open(encoding='utf-8', newline='') as file:
    reader = csv.DictReader(file)
    assert reader.fieldnames == ['song_id', 'song_name', 'artist', 'genres']
    songs = list(reader)
assert len({s['song_id'] for s in songs}) == len(songs)
assert all(s['song_name'].strip() and s['artist'].strip() for s in songs)
assert len({(min(names_for(s['artist'])), key(song_title(s['song_name']))) for s in songs}) == len(songs)
with (root / 'work/integration-check/data/processed/songs.csv').open(encoding='utf-8-sig', newline='') as file:
    original = list(csv.DictReader(file))
old = {(min(names_for(s['artist'])), key(song_title(s['song_name']))) for s in original}
overlap = sum((min(names_for(s['artist'])), key(song_title(s['song_name']))) in old for s in songs)
empty = [(n, ' | '.join(r['attempts'])) for n, r in states.items() if not r['tracks']]
partial = [(n, ' | '.join(r['attempts'])) for n, r in states.items() if any('cap' in a or 'partial' in a or 'top_window' in a for a in r['attempts'])]
write_csv(out / 'missing_artists.csv', ['artist', 'attempts'], empty)
write_csv(out / 'partial_artists.csv', ['artist', 'attempts'], partial)
with (out / 'sources.csv').open(encoding='utf-8', newline='') as file:
    source_counts = Counter(s['source'] for s in csv.DictReader(file))
report = {'artists_attempted': len(states), 'artists_with_songs': len(states) - len(empty), 'missing_artists': len(empty), 'partial_or_capped_artists': len(partial), 'deduplicated_songs': count, 'songs_with_genres': sum(bool(s['genres']) for s in songs), 'source_observations': dict(source_counts), 'old_rows': len(original), 'old_unique_name_artist_keys': len(old), 'overlap_with_existing_name_artist_keys': overlap, 'new_name_artist_keys': count - overlap, 'combined_name_artist_keys': len(old) + count - overlap}
(out / 'quality_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
