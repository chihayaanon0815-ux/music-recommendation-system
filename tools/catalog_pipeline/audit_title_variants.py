import csv
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, song_title, write_csv

root = Path(__file__).resolve().parents[2]
base = root/'outputs/全曲库-曲风补全/songs.csv'
out = root/'outputs/全量曲库-质量验收'
groups = defaultdict(list)
with base.open(encoding='utf-8', newline='') as handle:
    for row in csv.DictReader(handle):
        loose_title = ''.join(c for c in key(song_title(row['song_name'])) if c.isalnum())
        if len(loose_title) >= 2 and row['artist'].strip():
            groups[min(names_for(row['artist'])), loose_title].append(row)
result = []
for (artist, title), tracks in sorted(groups.items()):
    if len(tracks) < 2:
        continue
    for r in tracks:
        result.append((artist,title,r['song_id'],r['song_name'],r['artist'],r['genres'],len(tracks)))
write_csv(out/'title_punctuation_review.csv', ('artist_normalized','title_without_punctuation','song_id','song_name','artist','genres','group_size'), result)
print('Punctuation variants',len({(r[0],r[1]) for r in result}),'groups',len(result),'rows')
