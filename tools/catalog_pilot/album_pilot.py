import json,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path

root=Path('work/artist_pilot')
for path in sorted(root.glob('releases_*.json')):
    data=json.loads(path.read_text(encoding='utf-8'))
    albums=[r for r in data.get('releases',[]) if r.get('status')=='Official' and r.get('release-group',{}).get('primary-type')=='Album']
    if not albums:
        print(path.stem,'no official album on first page',flush=True); continue
    release=albums[0]
    url='https://musicbrainz.org/ws/2/release/'+release['id']+'?'+urllib.parse.urlencode({'inc':'recordings+artist-credits+release-groups','fmt':'json'})
    for attempt in range(3):
        time.sleep(1.2 if not attempt else 3*2**attempt)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=40) as f: album=json.load(f)
            (root/('album_'+release['id']+'.json')).write_text(json.dumps(album,ensure_ascii=False,indent=2),encoding='utf-8')
            count=sum(len(m.get('tracks',[])) for m in album.get('media',[]))
            print(path.stem,'album',release['title'],'tracks',count,flush=True)
            break
        except (urllib.error.URLError,TimeoutError) as exc: print('retry',attempt+1,exc,flush=True)
