"""Small MusicBrainz pilot; preserves raw artist candidates and recordings."""
import json, time, urllib.parse, urllib.request
from pathlib import Path

OUT = Path(__file__).parent / 'artist_pilot'
OUT.mkdir(exist_ok=True)
NAMES = ['周杰倫', '鄧麗君', '陈奕迅', 'The Beatles', 'BTS', '宇多田ヒカル']
BASE = 'https://musicbrainz.org/ws/2/'
HEADERS = {'User-Agent': 'CourseMusicCoveragePilot/1.0 (https://github.com/chihayaanon0815-ux/music-recommendation-system)', 'Accept': 'application/json'}

def get(path, params):
    url = BASE + path + '?' + urllib.parse.urlencode({**params, 'fmt': 'json'})
    time.sleep(1.2)
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as response:
        return json.load(response)

for name in NAMES:
    try:
        data = get('artist/', {'query': 'artist:"' + name + '"', 'limit': 5})
        (OUT / (str(NAMES.index(name)) + '.json')).write_text(json.dumps({'query': name, 'result': data}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(name, 'candidates', len(data.get('artists', [])), flush=True)
    except Exception as exc:
        print(name, type(exc).__name__, str(exc), flush=True)
