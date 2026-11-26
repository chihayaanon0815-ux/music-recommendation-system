"""Create auditable artist-name candidates; no automatic identity approval."""
import csv, json, sys, time, urllib.parse, urllib.request, urllib.error
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'outputs'; OUT.mkdir(exist_ok=True)
CACHE=ROOT/'work'/'artist_roster_cache'; CACHE.mkdir(exist_ok=True)
SOURCE=ROOT/'work'/'integration-check'/'data'/'processed'/'songs.csv'
counts=Counter(); chinese_tag=Counter()
with SOURCE.open(encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        name=row['artist'].strip()
        if name:
            counts[name]+=1
            if '华语流行' in row['genres'].split('|'):chinese_tag[name]+=1
with (OUT/'艺人名单-原始署名候选.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['artist_credit','song_count','mandopop_tag_count','entity_id','review_status','note'])
    for name,n in sorted(counts.items(),key=lambda x:(-x[1],x[0])):
        w.writerow([name,n,chinese_tag[name],'','未核对','完整署名，可能为合作组合；不按字符拆分'])

# Working seed names are a pilot, not a claim of comprehensive coverage or ranking.
seed=[('华语','周杰倫'),('华语','鄧麗君'),('华语','陳奕迅'),('华语','王菲'),('华语','張學友'),('华语','林俊傑'),('华语','蔡依林'),('华语','五月天'),('华语','張惠妹'),('华语','孫燕姿'),('华语','劉德華'),('华语','Beyond'),('华语','李宗盛'),('华语','薛之謙'),('华语','梁靜茹'),('华语','田馥甄'),('欧美','The Beatles'),('欧美','Taylor Swift'),('欧美','Queen'),('欧美','Michael Jackson'),('日韩','BTS'),('日韩','宇多田ヒカル'),('日韩','BLACKPINK'),('其他','A. R. Rahman')]
rows=[]
for i,(bucket,name) in enumerate(seed):
    path=CACHE/f'{i:03}.json'; data=None; error=''
    if path.exists(): data=json.loads(path.read_text(encoding='utf-8'))
    elif '--offline' in sys.argv:
        error='尚未查询（离线生成）'
    else:
        url='https://musicbrainz.org/ws/2/artist/?'+urllib.parse.urlencode({'query':'artist:"'+name+'"','limit':5,'fmt':'json'})
        for attempt in range(3):
            time.sleep(1.3 if not attempt else 5*2**attempt)
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)','Accept':'application/json'})
                with urllib.request.urlopen(req,timeout=30) as f:data=json.load(f)
                path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');break
            except (urllib.error.URLError,TimeoutError) as e:error=str(e)
    candidates=(data or {}).get('artists',[])
    for rank,a in enumerate(candidates,1):
        rows.append([bucket,name,rank,a.get('name',''),a.get('id',''),a.get('type',''),a.get('country',''),a.get('disambiguation',''),a.get('score',''),'待核对','https://musicbrainz.org/artist/'+a.get('id','')])
    if not candidates:rows.append([bucket,name,'','','','','','','','查询失败或无结果',error])
    print(i+1,name,len(candidates),error,flush=True)
with (OUT/'艺人名单-首批身份候选.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['覆盖规划','查询名称','候选序号','标准名称','musicbrainz_artist_id','实体类型','地区代码','区分说明','搜索得分','审核状态','来源网址或错误']);w.writerows(rows)
print('credits',len(counts),'seed names',len(seed),'candidate rows',len(rows))
