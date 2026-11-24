"""Conservative merged draft and auditable label normalization table."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from catalog import key, names_for, song_title, write_csv

root = Path(__file__).resolve().parents[2]
source = root / 'outputs/艺人扩充1000/采集结果'
out = root / 'outputs/清洗与标签统一草稿'
out.mkdir(exist_ok=True)

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)

def split_tags(value):
    return {s.strip() for s in value.split('|') if s.strip()}

# Explicit equivalent labels only. Other meanings remain visible for review.
aliases = {}
dimensions = {}
definitions = '''
流行;曲风;pop|流行樂|ポップ
华语流行;曲风;mandopop|華語流行樂|中文流行音樂
粤语流行;曲风;cantopop|Cantopop/HK-Pop|粵語流行樂
台湾流行;曲风;Tai-Pop|台灣流行樂
日语流行;曲风;j-pop|日本流行樂
韩语流行;曲风;k-pop|韓國流行樂
摇滚;曲风;rock|搖滾|搖滾樂|ロック
独立摇滚;曲风;indie rock|獨立搖滾
独立流行;曲风;indie pop|獨立流行樂
另类摇滚;曲风;alternative rock
硬摇滚;曲风;hard rock
迷幻摇滚;曲风;psychedelic rock
民谣摇滚;曲风;folk rock|Folk-Rock|民謠搖滾
蓝调摇滚;曲风;blues rock|Blues-Rock|藍調搖滾
流行摇滚;曲风;pop rock|Pop/Rock|流行樂/搖滾
民谣;曲风;folk|民謠
另类民谣;曲风;alternative folk|另類民謠
当代民谣;曲风;contemporary folk|當代民謠
乡村;曲风;country|鄉村樂
蓝草;曲风;bluegrass
蓝调;曲风;blues
爵士;曲风;jazz|爵士樂
酸爵士;曲风;acid jazz
酷派爵士;曲风;cool jazz
融合爵士;曲风;jazz fusion
自由爵士;曲风;free jazz
柔和爵士;曲风;smooth jazz
人声爵士;曲风;vocal jazz
当代爵士;曲风;contemporary jazz
古典;曲风;classical|古典音樂
古典跨界;曲风;Classical Crossover|古典跨界
歌剧;曲风;opera
室内乐;曲风;Chamber Music
管弦乐;曲风;orchestral|管弦樂
电子;曲风;electronic|電子音樂|エレクトロニック
电子乐;曲风;electronica|エレクトロニカ
浩室;曲风;house
深浩室;曲风;deep house
科技舞曲;曲风;techno
出神舞曲;曲风;trance
鼓打贝斯;曲风;drum and bass
回响贝斯;曲风;dubstep
碎拍;曲风;breakbeat|breaks
氛围;曲风;ambient|氛圍音樂
舞曲;曲风;dance|ダンス
迪斯科;曲风;disco
嘻哈;曲风;hip hop|Hip-Hop
嘻哈/说唱;曲风;Hip-Hop/Rap|嘻哈/饒舌
说唱;曲风;rap|饒舌
节奏布鲁斯;曲风;r&b
节奏布鲁斯/灵魂乐;曲风;R&B/Soul|R&B/靈魂樂
当代节奏布鲁斯;曲风;contemporary r&b|當代 R&B
灵魂乐;曲风;soul|靈魂樂
新灵魂乐;曲风;neo soul|Neo-Soul
放克;曲风;funk
雷鬼;曲风;reggae
斯卡;曲风;ska
朋克;曲风;punk
金属;曲风;metal|金屬樂
重金属;曲风;heavy metal
死亡金属;曲风;death metal
鞭击金属;曲风;thrash metal
流行朋克;曲风;pop punk
拉丁;地区曲风;latin
世界音乐;地区曲风;Worldwide|世界音樂
中国;地区;Chinese
亚洲;地区;Asia|亞洲
日本;地区;日本
阿拉伯;地区;Arabic
印度;地区;Indian
巴西;地区;Brazilian
俄罗斯;地区;Russian
法语流行;曲风;French Pop|法語流行樂
印度流行;曲风;Indian Pop|印度流行樂
古风/中国风;曲风;zhongguo feng
儿童音乐;受众;Children's Music|兒童音樂
动画音乐;用途;Anime|動畫|アニメ
影视原声;用途;Soundtrack|原聲帶
电视原声;用途;TV Soundtrack|電視原聲帶
原创配乐;用途;Original Score
音乐剧;用途;Musicals|musical|音樂劇
电子游戏;用途;電子遊戲
圣诞音乐;节庆;Christmas|christmas music
节庆音乐;节庆;Holiday|節慶
摇篮曲;用途;Lullabies
冥想;场景;Meditation
放松;场景;Relaxation
健身运动;场景;Fitness & Workout
自然声音;声音类型;Nature
纯音乐;声音类型;Instrumental|演奏曲
人声;声音类型;Vocal|聲樂
朗读;内容类型;Spoken Word|誦讀
访谈;内容类型;interview
喜剧;内容类型;Comedy
单口喜剧;内容类型;Standup Comedy
卡拉OK;版本;Karaoke|卡拉 OK
翻唱致敬;版本;Tribute
创作歌手;艺人类型;Singer/Songwriter|singer-songwriter|創作歌手
新世纪;曲风;New Age|新世紀
轻音乐;曲风;輕音樂
老歌;年代;Oldies
传统流行;曲风;Traditional Pop|傳統流行樂
'''
for line in definitions.strip().splitlines():
    canonical, dimension, values = line.split(';')
    for value in [canonical, *values.split('|')]:
        aliases[key(value)] = canonical
    dimensions[canonical] = dimension

raw_counts = Counter()
observed = defaultdict(set)
for row in read(source / 'sources.csv'):
    tags = split_tags(row['genres'])
    raw_counts.update(tags)
    observed[row['song_id']].update(tags)
for row in read(root / 'work/integration-check/data/processed/songs.csv'):
    raw_counts.update(split_tags(row['genres']))

def canonicalize(tags):
    return {aliases.get(key(t), key(t)) for t in tags}

mapping = []
for raw in sorted(raw_counts, key=str.casefold):
    canonical = aliases.get(key(raw), key(raw))
    mapping.append((raw, canonical, dimensions.get(canonical, ''),
                    '明确同义/翻译映射草稿' if key(raw) in aliases else '仅规范字形大小写，语义待核对', raw_counts[raw]))
write_csv(out / 'label_mapping_review.csv', ['raw_label','canonical_label','dimension','status','source_record_count'], mapping)
write_csv(out / 'label_review_pending.csv', ['raw_label','canonical_label','dimension','status','source_record_count'],
          [row for row in mapping if row[3].startswith('仅')])

groups = {}
evidence = []
removed = []
for input_name, path in [('original', root/'work/integration-check/data/processed/songs.csv'), ('collected', source/'songs_candidates.csv')]:
    for row in read(path):
        row = {k: (row.get(k) or '').strip() for k in ('song_id','song_name','artist','genres')}
        if not row['song_id'] or not row['song_name']:
            removed.append((input_name, row['song_id'], 'missing_id_or_title'))
            continue
        name = song_title(row['song_name'])
        identity = (min(names_for(row['artist'])), key(name))
        # An empty artist does not provide enough evidence for name-based merging.
        if not row['artist']:
            identity = (input_name + ':' + row['song_id'], key(name))
        raw_tags = split_tags(row['genres'])
        if input_name == 'collected':
            raw_tags.update(observed[row['song_id']])
        if identity not in groups:
            groups[identity] = {'row': {**row, 'song_name':name}, 'tags':set()}
        groups[identity]['tags'].update(raw_tags)
        evidence.append((identity,input_name,row['song_id'],row['song_name'],row['artist'],row['genres']))

result = []
ids = {}
for identity, group in sorted(groups.items()):
    row = group['row']
    sid = row['song_id']
    if sid in ids:
        sid = 'clean:' + hashlib.sha256('\0'.join(identity).encode()).hexdigest()[:24]
    ids[sid] = identity
    group['final_id'] = sid
    result.append((sid,row['song_name'],row['artist'],'|'.join(sorted(canonicalize(group['tags'])))))
assert len(result) == len({row[0] for row in result})
write_csv(out/'songs.csv', ['song_id','song_name','artist','genres'],result)
write_csv(out/'unlabeled_songs.csv', ['song_id','song_name','artist','genres'], [row for row in result if not row[3]])
write_csv(out/'row_lineage.csv', ['song_id','input','original_id','original_title','original_artist','original_genres'],
          [(groups[i]['final_id'],*values) for i,*values in evidence])
write_csv(out/'removed_rows.csv', ['input','original_id','reason'],removed)
genre_counts = Counter(g for row in result for g in split_tags(row[3]))
write_csv(out/'genre_counts.csv', ['genre','count'], sorted(genre_counts.items(),key=lambda x:(-x[1],x[0])))
report = {'input_rows':len(evidence)+len(removed),'output_rows':len(result),'removed_invalid_rows':len(removed),
          'merged_rows':len(evidence)-len(result),'raw_label_spellings':len(raw_counts),'normalized_label_spellings':len({r[1] for r in mapping}),
          'labels_needing_semantic_review':sum(r[3].startswith('仅') for r in mapping),
          'unique_labels_needing_semantic_review':len({r[1] for r in mapping if r[3].startswith('仅')}),
          'rows_with_labels':sum(bool(row[3]) for row in result),'rows_without_labels':sum(not row[3] for row in result),
          'scope':'清洗草稿，合并来源标签后仍需核对标签冲突、身份及版本归并'}
(out/'cleanup_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
