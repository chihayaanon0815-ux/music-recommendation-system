"""Fetch representative releases, preserving response and progress for resumption."""
import json,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path

ROOT=Path('work/full_release_pilot')
OUT=Path('work/release_tracks');OUT.mkdir(exist_ok=True)
IDS=['a223958d-5c56-4b2c-a30a-87e357bc121b','5c5cb762-d95e-47af-a7bf-35171eeab8e6','86119d30-d930-4e65-a97a-e31e22388166']
for aid in IDS:
    folder=ROOT/aid
    if not (folder/'complete.json').exists(): raise RuntimeError('incomplete release browse: '+aid)
    releases=[]
    for p in sorted(folder.glob('[0-9]*.json')): releases.extend(json.loads(p.read_text(encoding='utf-8')).get('releases',[]))
    # One representative per release group; selecting 5 groups per artist is a pilot, not full coverage.
    eligible=[]
    for r in releases:
        group=r.get('release-group') or {}; typ=group.get('primary-type'); secondary=group.get('secondary-types') or []
        if r.get('status')!='Official' or typ not in ('Album','EP','Single') or set(secondary)&{'Live','Compilation','Remix','DJ-mix','Interview','Spokenword','Audiobook'} or not group.get('id'):continue
        eligible.append(r)
    eligible.sort(key=lambda r:(r.get('date') or '9999',r['id']))
    groups={}
    for r in eligible:groups.setdefault(r['release-group']['id'],r)
    selected=list(groups.values())[:5]
    print(aid,'eligible groups',len(groups),'pilot selected',len(selected),flush=True)
    for release in selected:
        rid=release['id']; path=OUT/(rid+'.json')
        if path.exists():continue
        url='https://musicbrainz.org/ws/2/release/'+rid+'?'+urllib.parse.urlencode({'inc':'recordings+artist-credits+release-groups','fmt':'json'})
        for attempt in range(4):
            time.sleep(1.3 if attempt==0 else min(60,5*2**attempt))
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)','Accept':'application/json'})
                with urllib.request.urlopen(req,timeout=45) as f:data=json.load(f)
                path.write_text(json.dumps({'target_artist':aid,'release':data},ensure_ascii=False,indent=2),encoding='utf-8')
                print(rid,'tracks',sum(len(m.get('tracks',[])) for m in data.get('media',[])),flush=True);break
            except (urllib.error.URLError,TimeoutError) as e: print(rid,'retry',attempt+1,str(e),flush=True)
        else: print(rid,'FAILED',flush=True)
