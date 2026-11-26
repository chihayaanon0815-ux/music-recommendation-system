"""Resumable MusicBrainz artist and release collector. Candidate data only."""
import argparse,csv,json,sqlite3,time,urllib.error,urllib.parse,urllib.request,unicodedata
from pathlib import Path

def key(s): return ' '.join(unicodedata.normalize('NFKC',s).casefold().split())
def request(path, params):
    url='https://musicbrainz.org/ws/2/'+path+'?'+urllib.parse.urlencode({**params,'fmt':'json'})
    for n in range(5):
        time.sleep(1.3 if n==0 else min(60,5*2**n))
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=35) as response:return json.load(response)
        except (urllib.error.URLError,TimeoutError) as exc:
            print('retry',n+1,path,str(exc),flush=True)
    raise RuntimeError('request failed: '+url)

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True,help='CSV containing artist_credit or artist column');p.add_argument('--work',default='work/music_collector/state');p.add_argument('--max-artists',type=int,default=20);p.add_argument('--max-releases-per-artist',type=int,default=0,help='0 means no cap');p.add_argument('--max-records',type=int,default=120000,help='stop after this many unique candidate recordings; not a cleaned-song target');args=p.parse_args()
    if args.max_artists<=0 or args.max_releases_per_artist<0 or args.max_records<=0:p.error('limits must be positive, release limit may be zero')
    root=Path(args.work);root.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(root/'collector.sqlite3');db.executescript('''
    CREATE TABLE IF NOT EXISTS artists (credit TEXT PRIMARY KEY, mbid TEXT, status TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS pages (artist_id TEXT, offset INTEGER, body TEXT, PRIMARY KEY(artist_id,offset));
    CREATE TABLE IF NOT EXISTS releases (artist_id TEXT, release_id TEXT, group_id TEXT, status TEXT, body TEXT, PRIMARY KEY(artist_id,release_id));
    CREATE TABLE IF NOT EXISTS observations (artist_id TEXT, release_id TEXT, group_id TEXT, recording_id TEXT, title TEXT, artist TEXT, PRIMARY KEY(artist_id,release_id,recording_id,title));
    ''')
    with open(args.input,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);field=next((n for n in ('artist_credit','artist','候选名称') if n in (reader.fieldnames or [])),None)
        if not field:raise ValueError('input must include artist_credit, artist, or 候选名称')
        names=list(dict.fromkeys(row[field].strip() for row in reader if row.get(field,'').strip()))[:args.max_artists]
    for idx,name in enumerate(names,1):
        row=db.execute('SELECT mbid,status FROM artists WHERE credit=?',(name,)).fetchone()
        if row and row[1] in ('ambiguous','no_match'):continue
        try:
            if not row:
                result=request('artist/',{'query':'artist:"'+name.replace('"','')+'"','limit':10})
                candidates=result.get('artists',[]); exact=[a for a in candidates if key(a.get('name',''))==key(name)]
                if len(exact)!=1:
                    status='ambiguous' if len(exact)>1 else 'no_match';db.execute('INSERT OR REPLACE INTO artists VALUES(?,?,?,?)',(name,'',status,json.dumps(candidates,ensure_ascii=False)));db.commit();print(idx,name,status,flush=True);continue
                mbid=exact[0]['id'];db.execute('INSERT OR REPLACE INTO artists VALUES(?,?,?,?)',(name,mbid,'matched_unverified',json.dumps(exact[0],ensure_ascii=False)));db.commit()
            else:mbid=row[0]
            offset=0;releases=[]
            while True:
                cached=db.execute('SELECT body FROM pages WHERE artist_id=? AND offset=?',(mbid,offset)).fetchone()
                if cached:data=json.loads(cached[0])
                else:
                    data=request('release/',{'artist':mbid,'limit':100,'offset':offset,'inc':'release-groups+artist-credits'});db.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?)',(mbid,offset,json.dumps(data,ensure_ascii=False)));db.commit()
                items=data.get('releases',[]);total=data.get('release-count')
                if total is None:raise RuntimeError('missing release-count')
                releases.extend(items);offset+=len(items)
                if offset>=total:break
                if not items:raise RuntimeError('incomplete release pagination')
            eligible=[]
            for r in releases:
                g=r.get('release-group') or {};secondary=set(g.get('secondary-types') or [])
                if r.get('status')=='Official' and g.get('id') and g.get('primary-type') in ('Album','EP','Single') and not secondary.intersection({'Live','Compilation','Remix','DJ-mix','Interview','Spokenword','Audiobook'}):eligible.append(r)
            eligible.sort(key=lambda r:(r.get('date') or '9999',r['id']));chosen={}
            for r in eligible:chosen.setdefault(r['release-group']['id'],r)
            selected=list(chosen.values())[:args.max_releases_per_artist or None]
            for release in selected:
                rid=release['id'];gid=release['release-group']['id']
                old=db.execute('SELECT status FROM releases WHERE artist_id=? AND release_id=?',(mbid,rid)).fetchone()
                if old:continue
                detail=request('release/'+rid,{'inc':'recordings+artist-credits+release-groups'})
                entries=[]
                for medium in detail.get('media',[]):
                    for track in medium.get('tracks',[]):
                        rec=track.get('recording') or {};recid=rec.get('id','');title=(rec.get('title') or track.get('title') or '').strip()
                        credits=rec.get('artist-credit') or track.get('artist-credit') or []
                        artist=''.join(c.get('name',c.get('artist',{}).get('name',''))+c.get('joinphrase','') for c in credits if isinstance(c,dict)).strip()
                        if recid and title and artist:entries.append((mbid,rid,gid,recid,title,artist))
                with db:
                    db.execute('INSERT INTO releases VALUES(?,?,?,?,?)',(mbid,rid,gid,'ok' if entries else 'empty_review',json.dumps(detail,ensure_ascii=False)))
                    db.executemany('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?)',entries)
                count=db.execute('SELECT count(DISTINCT recording_id) FROM observations').fetchone()[0]
                print(idx,name,'release',rid,'tracks',len(entries),'unique recordings',count,flush=True)
                if count>=args.max_records:break
            if db.execute('SELECT count(DISTINCT recording_id) FROM observations').fetchone()[0]>=args.max_records:break
        except (RuntimeError,ValueError,KeyError) as exc:
            print('FAILED',name,str(exc),flush=True)
    export(db,root)

def export(db,root):
    rows=db.execute('SELECT recording_id,min(title),min(artist) FROM observations GROUP BY recording_id ORDER BY recording_id').fetchall()
    with (root/'songs_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['song_id','song_name','artist','genres']);w.writerows(('mbid:'+r,t,a,'') for r,t,a in rows)
    with (root/'provenance.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['target_artist_mbid','release_id','release_group_id','recording_id','title','artist']);w.writerows(db.execute('SELECT * FROM observations ORDER BY artist_id,release_id,recording_id'))
    with (root/'artist_status.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['artist_credit','musicbrainz_artist_id','status','candidate_json']);w.writerows(db.execute('SELECT * FROM artists ORDER BY credit'))
    print('EXPORTED',len(rows),'candidate recordings to',root,flush=True)

if __name__=='__main__':main()
