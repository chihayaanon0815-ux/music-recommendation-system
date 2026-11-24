import csv, json
from pathlib import Path

out = Path('outputs')
out.mkdir(exist_ok=True)
files = sorted(Path('work/artist_pilot').glob('recordings_*.json'))
rows = {}
for path in files:
    data = json.loads(path.read_text(encoding='utf-8'))
    for r in data.get('recordings', []):
        credit = ''.join(a.get('name', a.get('artist', {}).get('name', '')) + a.get('joinphrase', '') for a in r.get('artist-credit', []) if isinstance(a, dict)).strip()
        tags = sorted({g['name'].strip() for g in r.get('genres', []) if g.get('name', '').strip()})
        rows[r['id']] = {'song_id':'mbid:'+r['id'], 'song_name':r.get('title','').strip(), 'artist':credit, 'genres':'|'.join(tags)}
with (out / 'MusicBrainz试采集-录音候选.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['song_id','song_name','artist','genres']); writer.writeheader(); writer.writerows(rows.values())
print('unique recordings',len(rows),'missing name or artist',sum(not r['song_name'] or not r['artist'] for r in rows.values()),'tagged',sum(bool(r['genres']) for r in rows.values()))
