"""Export only exact recording-ID deduplicated candidates, with provenance."""
import csv,json
from collections import defaultdict
from pathlib import Path

def credits(items):
    return ''.join(i.get('name',i.get('artist',{}).get('name',''))+i.get('joinphrase','') for i in (items or []) if isinstance(i,dict)).strip()

rows={}; evidence=[]
for path in sorted(Path('work/release_tracks').glob('*.json')):
    raw=json.loads(path.read_text(encoding='utf-8')); release=raw['release']; target=raw['target_artist']
    for medium in release.get('media',[]):
        for track in medium.get('tracks',[]):
            rec=track.get('recording') or {};rid=rec.get('id')
            if not rid: continue
            name=(rec.get('title') or track.get('title') or '').strip()
            artist=credits(rec.get('artist-credit')) or credits(track.get('artist-credit'))
            rows.setdefault(rid,{'song_id':'mbid:'+rid,'song_name':name,'artist':artist,'genres':''})
            evidence.append({'song_id':'mbid:'+rid,'target_artist_mbid':target,'release_id':release['id'],'release_group_id':(release.get('release-group') or {}).get('id',''),'release_title':release.get('title',''),'track_title':track.get('title',''),'recording_title':name})
out=Path('outputs');out.mkdir(exist_ok=True)
for name,fields,data in [('华语艺人-发行曲目候选.csv',['song_id','song_name','artist','genres'],rows.values()),('华语艺人-曲目来源记录.csv',['song_id','target_artist_mbid','release_id','release_group_id','release_title','track_title','recording_title'],evidence)]:
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
print('releases',len(list(Path('work/release_tracks').glob('*.json'))),'tracks',len(evidence),'unique recording IDs',len(rows),'missing name or artist',sum(not r['song_name'] or not r['artist'] for r in rows.values()))
