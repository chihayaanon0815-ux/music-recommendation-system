"""Resumeable artist release browse; preserves source responses unmodified."""
import json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

artists = {'周杰倫':'a223958d-5c56-4b2c-a30a-87e357bc121b','鄧麗君':'5c5cb762-d95e-47af-a7bf-35171eeab8e6','陳奕迅':'86119d30-d930-4e65-a97a-e31e22388166','BTS':'0d79fe8e-ba27-4859-bb8c-2f255f346853','宇多田ヒカル':'b539e453-c4fe-47e3-8a07-8517eac74429'}
root=Path('work/full_release_pilot');root.mkdir(exist_ok=True)
for name,mbid in artists.items():
    folder=root/mbid;folder.mkdir(exist_ok=True);offset=0
    while True:
        path=folder/f'{offset:06}.json'
        if path.exists(): data=json.loads(path.read_text(encoding='utf-8'))
        else:
            url='https://musicbrainz.org/ws/2/release/?'+urllib.parse.urlencode({'artist':mbid,'limit':100,'offset':offset,'inc':'release-groups+artist-credits','fmt':'json'})
            data=None
            for attempt in range(4):
                time.sleep(1.3 if attempt==0 else min(60,5*2**attempt))
                try:
                    req=urllib.request.Request(url,headers={'User-Agent':'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)','Accept':'application/json'})
                    with urllib.request.urlopen(req,timeout=45) as f:data=json.load(f)
                    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');break
                except (urllib.error.URLError,TimeoutError) as e: print(name,offset,'retry',attempt+1,str(e),flush=True)
            if data is None:
                (folder/'incomplete.txt').write_text(f'failed offset {offset}',encoding='utf-8');break
        items=data.get('releases',[]);total=data.get('release-count')
        print(name,'offset',offset,'got',len(items),'total',total,flush=True)
        offset+=len(items)
        if total is None or not items:
            (folder/'incomplete.txt').write_text(f'unexpected pagination offset {offset}',encoding='utf-8');break
        if offset>=total:
            (folder/'complete.json').write_text(json.dumps({'artist':name,'artist_id':mbid,'count':offset,'reported_total':total},ensure_ascii=False),encoding='utf-8')
            old=folder/'incomplete.txt'
            if old.exists():old.unlink()
            break
