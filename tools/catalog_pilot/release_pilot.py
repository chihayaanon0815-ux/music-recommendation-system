import json,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path

root=Path('work/artist_pilot')
for file in sorted(root.glob('recordings_*.json')):
    mbid=file.stem.removeprefix('recordings_')
    url='https://musicbrainz.org/ws/2/release/?'+urllib.parse.urlencode({'artist':mbid,'limit':100,'inc':'release-groups+artist-credits','fmt':'json'})
    for attempt in range(3):
        time.sleep(1.2 if attempt==0 else 3*2**attempt)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=40) as f: data=json.load(f)
            (root/('releases_'+mbid+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            releases=data.get('releases',[])
            print(mbid,'total',data.get('release-count'),'sample',len(releases),'official',sum(r.get('status')=='Official' for r in releases),flush=True)
            break
        except (urllib.error.URLError,TimeoutError) as exc: print('retry',attempt+1,exc,flush=True)
