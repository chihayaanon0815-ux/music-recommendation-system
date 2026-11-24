import json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

OUT = Path(__file__).parent / 'artist_pilot'
ARTISTS = {'周杰倫':'a223958d-5c56-4b2c-a30a-87e357bc121b','鄧麗君':'5c5cb762-d95e-47af-a7bf-35171eeab8e6','陳奕迅':'86119d30-d930-4e65-a97a-e31e22388166','BTS':'0d79fe8e-ba27-4859-bb8c-2f255f346853','宇多田ヒカル':'b539e453-c4fe-47e3-8a07-8517eac74429'}
for name, mbid in ARTISTS.items():
    url = 'https://musicbrainz.org/ws/2/recording/?' + urllib.parse.urlencode({'artist':mbid,'limit':100,'inc':'artist-credits+genres+isrcs','fmt':'json'})
    for attempt in range(3):
        time.sleep(1.2 if not attempt else 3 * 2**attempt)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=40) as f: data=json.load(f)
            (OUT / ('recordings_'+mbid+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            records=data.get('recordings',[])
            print(name,'total',data.get('recording-count'),'sample',len(records),'with genres',sum(bool(r.get('genres')) for r in records),flush=True)
            break
        except (urllib.error.URLError,TimeoutError) as e:
            print(name,'attempt',attempt+1,str(e),flush=True)
