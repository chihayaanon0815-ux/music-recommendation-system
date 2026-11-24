"""Conservative audit, never merges candidate recordings into the production CSV."""
import csv, json, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

def norm(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())

root=Path('work/artist_pilot')
source=Path('work/integration-check/data/processed/songs.csv')
index=defaultdict(list)
with source.open(encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f): index[(norm(row['song_name']),norm(row['artist']))].append(row)
totals=Counter()
for path in root.glob('recordings_*.json'):
    records=json.loads(path.read_text(encoding='utf-8')).get('recordings',[])
    for record in records:
        artist=''.join(a.get('name',a.get('artist',{}).get('name',''))+a.get('joinphrase','') for a in record.get('artist-credit',[]) if isinstance(a,dict)).strip()
        match=index.get((norm(record.get('title','')),norm(artist)),[])
        totals['recordings']+=1
        totals['exact_name_artist_candidates']+=bool(match)
        totals['has_recording_genre']+=bool(record.get('genres'))
        totals['multiple_existing_candidates']+=len(match)>1
print(dict(totals))
