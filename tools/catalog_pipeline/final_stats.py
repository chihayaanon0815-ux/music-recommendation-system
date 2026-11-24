"""Wait for the current deep run to end, then publish final statistics."""
import csv
import json
import time
from collections import Counter
from pathlib import Path

from catalog import export, key, names_for, song_title, write_csv

root = Path(__file__).resolve().parents[2]
work = root / 'work/catalog_1000'
out = root / 'outputs/艺人扩充1000/采集结果'
completion = root / 'work/catalog-completion.log'
while True:
    if completion.exists() and 'Deep query process exited' in completion.read_text(encoding='utf-8', errors='replace'):
        break
    time.sleep(10)

regular = json.loads((work / 'progress.json').read_text(encoding='utf-8'))
deep = json.loads((work / 'deep.json').read_text(encoding='utf-8'))
combined = dict(regular)
for name, result in deep.items():
    old = regular.get(name, {'tracks': [], 'attempts': []})
    combined[name] = {
        'tracks': list(dict.fromkeys(tuple(t) for t in old['tracks'] + result['tracks'])),
        'attempts': ['initial:' + a for a in old['attempts']] + ['deep:' + a for a in result['attempts']],
    }
export(out, combined)
with (out / 'songs_candidates.csv').open(encoding='utf-8', newline='') as file:
    reader = csv.DictReader(file)
    assert reader.fieldnames == ['song_id', 'song_name', 'artist', 'genres']
    songs = list(reader)
with (root / 'work/integration-check/data/processed/songs.csv').open(encoding='utf-8-sig', newline='') as file:
    old = list(csv.DictReader(file))
def identity(row):
    return min(names_for(row['artist'])), key(song_title(row['song_name']))
old_keys = {identity(row) for row in old}
new_keys = {identity(row) for row in songs}
assert len(new_keys) == len(songs)
assert len({r['song_id'] for r in songs}) == len(songs)
assert all(r['song_name'].strip() and r['artist'].strip() for r in songs)
with (out / 'sources.csv').open(encoding='utf-8', newline='') as file:
    observations = Counter(r['source'] for r in csv.DictReader(file))
missing = [(n, ' | '.join(r['attempts'])) for n, r in combined.items() if not r['tracks']]
unresolved = [(n, ' | '.join(r['attempts'])) for n, r in deep.items()
              if not r['tracks'] or any('partial' in a or 'cap' in a or 'error' in a.lower()
                                        or 'ambiguous' in a or 'worker_error' in a for a in r['attempts'])]
write_csv(out / 'missing_artists.csv', ['artist', 'attempts'], missing)
write_csv(out / 'unresolved_deep_artists.csv', ['artist', 'attempts'], unresolved)
tagged = sum(bool(row['genres'].strip()) for row in songs)
def genre_counts(rows):
    return Counter(tag.strip() for row in rows for tag in set(row['genres'].split('|')) if tag.strip())
new_genres = genre_counts(songs)
old_genres = genre_counts(old)
write_csv(out / 'all_genres.csv', ['genre', 'collected_song_count', 'original_song_count'],
          [(tag, new_genres[tag], old_genres[tag]) for tag in sorted(new_genres.keys() | old_genres.keys(), key=str.casefold)])
report = {
    'initial_artists_attempted': len(regular), 'deep_artists_attempted': len(deep),
    'artists_with_songs': len(combined) - len(missing), 'missing_artists': len(missing),
    'deep_records_needing_review': len(unresolved), 'unique_candidate_songs': len(songs),
    'songs_with_genres': tagged, 'songs_missing_genres': len(songs) - tagged,
    'genre_coverage_percent': round(100 * tagged / len(songs), 2) if songs else 0,
    'collected_genre_spellings': len(new_genres), 'all_genre_spellings': len(new_genres.keys() | old_genres.keys()),
    'source_observations': dict(observations), 'original_rows': len(old),
    'original_name_artist_keys': len(old_keys), 'overlap_name_artist_keys': len(new_keys & old_keys),
    'new_name_artist_keys': len(new_keys - old_keys), 'combined_name_artist_keys': len(new_keys | old_keys),
    'complete_artist_pass': len(deep) == 1000,
    'coverage_rule': '同名同艺人及已知别名、简繁和部分版本后缀归一化，歌曲身份和平台目录完整性仍需核查',
}
(out / 'final_statistics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
summary = {'planned_artists': 1000, 'initial_completed': len(regular), 'deep_attempted': len(deep),
           'unique_candidate_songs': len(songs), 'deep_process_running': False}
(out / 'deep_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
