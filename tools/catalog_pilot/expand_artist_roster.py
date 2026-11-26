"""Build a broad working roster, preserve unverified identity and source credits."""
import csv,json,unicodedata
from collections import Counter
from pathlib import Path

root=Path(__file__).resolve().parent.parent
source=root/'work/integration-check/data/processed/songs.csv'
out=root/'outputs';out.mkdir(exist_ok=True)
groups={
'华语':'''周杰伦|邓丽君|陈奕迅|王菲|张学友|刘德华|郭富城|黎明|林俊杰|蔡依林|五月天|张惠妹|孙燕姿|李宗盛|薛之谦|梁静茹|田馥甄|Beyond|黄家驹|张国荣|梅艳芳|谭咏麟|陈慧娴|王杰|周华健|齐秦|罗大佑|崔健|窦唯|许巍|汪峰|朴树|郑钧|李健|毛不易|华晨宇|邓紫棋|张靓颖|李宇春|周笔畅|张杰|林忆莲|莫文蔚|杨千嬅|容祖儿|陈奕迅|谢霆锋|古巨基|郑秀文|陈小春|林子祥|叶倩文|草蜢|达明一派|苏打绿|伍佰 & China Blue|伍佰|动力火车|信乐团|F.I.R.|S.H.E|飞儿乐团|凤凰传奇|筷子兄弟|逃跑计划|痛仰乐队|新裤子|万能青年旅店|二手玫瑰|黑豹乐队|唐朝乐队|刺猬乐队|后海大鲨鱼|落日飞车|告五人|茄子蛋|八三夭|理想混蛋|草东没有派对|陈绮贞|卢广仲|韦礼安|徐佳莹|杨丞琳|王心凌|萧亚轩|萧敬腾|张韶涵|范玮琪|戴佩妮|陶喆|王力宏|方大同|潘玮柏|周传雄|任贤齐|光良|品冠|许美静|阿杜|孙楠|韩红|那英|田震|许嵩|汪苏泷|徐良|许佳豪|单依纯|周深|张碧晨|郁可唯|谭维维|张信哲|费玉清|蔡琴|刘若英|辛晓琪|孟庭苇|苏芮|齐豫|蔡健雅|陈洁仪|黄小琥|伍思凯|庾澄庆|张震岳|热狗| MC HotDog|蛋堡|陈珊妮|黄品源|张雨生|张洪量|任素汐|赵雷|宋冬野|陈粒|房东的猫|花粥|马頔|李志|陈鸿宇|陈楚生|许飞|许冠杰|张敬轩|陈奕迅|林家谦|李克勤|许志安|侧田|泳儿|卫兰|邓丽欣|陈柏宇|谢安琪|陈慧琳|王菀之|Twins|陈百强|黄凯芹|张智霖|张卫健|郑伊健|梁汉文|郑中基|黄耀明|林忆莲|陈慧娴|王若琳|魏如萱|徐怀钰|蔡依林|庞龙|刀郎|腾格尔|凤凰传奇|二手玫瑰|五条人|马赛克乐队|康姆士|陈婧霏|张悬|安溥|陈升|李荣浩|汪峰|梁博|陈奕迅''',
'欧美':'''The Beatles|Queen|Michael Jackson|Taylor Swift|Adele|Beyoncé|Rihanna|Lady Gaga|Bruno Mars|Ed Sheeran|Coldplay|Radiohead|Nirvana|Linkin Park|Green Day|Oasis|The Rolling Stones|Pink Floyd|Led Zeppelin|ABBA|Elton John|David Bowie|Madonna|Whitney Houston|Mariah Carey|Céline Dion|Britney Spears|Katy Perry|Ariana Grande|Billie Eilish|Lana Del Rey|Dua Lipa|The Weeknd|Justin Bieber|Eminem|Kendrick Lamar|Drake|Kanye West|Jay-Z|Snoop Dogg|2Pac|Bob Dylan|Bob Marley & The Wailers|Stevie Wonder|Aretha Franklin|Frank Sinatra|Ella Fitzgerald|Louis Armstrong|Miles Davis|John Coltrane|Nina Simone|Metallica|AC/DC|Guns N' Roses|Red Hot Chili Peppers|Foo Fighters|U2|Imagine Dragons|OneRepublic|Maroon 5|The Weeknd|Daft Punk|Avicii|Calvin Harris|Adele|Sia|Shakira|Enrique Iglesias|Bad Bunny|Ricky Martin|Luis Miguel|Rosalía|Andrea Bocelli|Enya''',
'日韩':'''BTS|BLACKPINK|宇多田ヒカル|米津玄師|YOASOBI|Ado|あいみょん|Official髭男dism|RADWIMPS|ONE OK ROCK|King Gnu|嵐|安室奈美恵|浜崎あゆみ|椎名林檎|中島美嘉|中森明菜|松田聖子|坂本龍一|久石譲|L'Arc〜en〜Ciel|X JAPAN|B'z|Mr.Children|サザンオールスターズ|SEKAI NO OWARI|TWICE|NewJeans|SEVENTEEN|EXO|BIGBANG|IU|少女時代|SHINee|Red Velvet|aespa|Stray Kids|LE SSERAFIM|IVE|PSY|BoA|G-DRAGON''',
'其他地区':'''A. R. Rahman|Arijit Singh|Lata Mangeshkar|Nusrat Fateh Ali Khan|Fela Kuti|Burna Boy|Wizkid|Miriam Makeba|Youssou N'Dour|Cesária Évora|Caetano Veloso|Gilberto Gil|Anitta|Mercedes Sosa|Astor Piazzolla|Fairuz|Umm Kulthum|Amr Diab|Tarkan|Ofra Haza|Tinariwen|Ali Farka Touré|Édith Piaf|Stromae|Angèle|ABBA|a-ha'''}

def norm(x):return ' '.join(unicodedata.normalize('NFKC',x).casefold().split())
counts=Counter();tags=Counter()
with source.open(encoding='utf-8-sig',newline='') as f:
 for r in csv.DictReader(f):
  name=r['artist'].strip()
  if name:counts[name]+=1;tags[name]+=int('华语流行' in r['genres'].split('|'))
lookup={norm(k):k for k in counts}
cache=root/'work/artist_roster_cache'
seed=['周杰倫','鄧麗君','陳奕迅','王菲','張學友','林俊傑','蔡依林','五月天','張惠妹','孫燕姿','劉德華','Beyond','李宗盛','薛之謙','梁靜茹','田馥甄','The Beatles','Taylor Swift','Queen','Michael Jackson','BTS','宇多田ヒカル','BLACKPINK','A. R. Rahman']
resolved={}
for i,n in enumerate(seed):
 p=cache/f'{i:03}.json'
 if p.exists():
  data=json.loads(p.read_text(encoding='utf-8')); c=data.get('artists',[])
  if len(c)==1 and str(c[0].get('score'))=='100': resolved[n]=c[0]
aliases={'周杰伦':'周杰倫','邓丽君':'鄧麗君','陈奕迅':'陳奕迅','张学友':'張學友','林俊杰':'林俊傑','蔡依林':'蔡依林','张惠妹':'張惠妹','孙燕姿':'孫燕姿','刘德华':'劉德華','李宗盛':'李宗盛','薛之谦':'薛之謙'}
seen=set();rows=[]
for region, names in groups.items():
 for name in (n.strip() for n in names.split('|')):
  if not name or norm(name) in seen:continue
  seen.add(norm(name)); match=lookup.get(norm(name),''); hit=resolved.get(aliases.get(name,name))
  rows.append([region,name,match,counts[match] if match else '',tags[match] if match else '',hit.get('id','') if hit else '',hit.get('name','') if hit else '', '单一搜索候选，待身份核对' if hit else '待查询并核对','人工拟定首版候选；地区为覆盖规划，不代表国籍或语种'])
with (out/'艺人名单-扩充候选首版.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['覆盖规划','候选名称','现有曲库精确署名','现有歌曲数','华语流行标签数','MusicBrainz候选ID','标准名称候选','状态','说明']);w.writerows(rows)
print('curated',len(rows),'exact existing credits',sum(bool(r[2]) for r in rows),'single matches pending review',sum(bool(r[5]) for r in rows))
