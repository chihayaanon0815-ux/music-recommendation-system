"""Summarize fetched pages, retaining incomplete collection status."""
import csv,json
from collections import Counter
from pathlib import Path

root=Path('work/full_release_pilot'); out=Path('outputs');out.mkdir(exist_ok=True)
rows=[]
for folder in sorted(p for p in root.iterdir() if p.is_dir()):
    complete=folder/'complete.json'; meta=json.loads(complete.read_text(encoding='utf-8')) if complete.exists() else {'artist_id':folder.name,'artist':'未完成','reported_total':''}
    releases=[]
    for path in sorted(folder.glob('[0-9]*.json')):
        releases.extend(json.loads(path.read_text(encoding='utf-8')).get('releases',[]))
    counts=Counter((r.get('status') or 'unknown') for r in releases)
    groups={r.get('release-group',{}).get('id') for r in releases if r.get('release-group',{}).get('id')}
    secondary=Counter(s for r in releases for s in r.get('release-group',{}).get('secondary-types',[]))
    rows.append({'艺人':meta['artist'],'艺人MBID':folder.name,'状态':'分页完成' if complete.exists() else '未完成','接口总发行数':meta.get('reported_total',''),'已取得发行记录数':len(releases),'不同发行组数':len(groups),'Official发行数':counts['Official'],'Live发行记录数':secondary['Live'],'Compilation发行记录数':secondary['Compilation'],'Remix发行记录数':secondary['Remix']})
with (out/'试点艺人-发行目录统计.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['艺人','艺人MBID','状态','接口总发行数','已取得发行记录数','不同发行组数','Official发行数','Live发行记录数','Compilation发行记录数','Remix发行记录数']);writer.writeheader();writer.writerows(rows)
print('artists',len(rows),'complete',sum(x['状态']=='分页完成' for x in rows))
