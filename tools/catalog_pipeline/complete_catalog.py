"""Continue the current run through full-discography queries and publish progress."""
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

from catalog import export, replace_file

root = Path(__file__).resolve().parents[2]
work = root / 'work/catalog_1000'
artists = root / 'outputs/艺人扩充1000/artists_1000.csv'
target = root / 'outputs/艺人扩充1000/采集结果'
with artists.open(encoding='utf-8', newline='') as file:
    total = len(list(csv.DictReader(file)))
while True:
    regular = json.loads((work / 'progress.json').read_text(encoding='utf-8'))
    if len(regular) >= total:
        break
    time.sleep(10)

log_path = root / 'work/catalog-1000-deep.log'
with log_path.open('a', encoding='utf-8') as log:
    process = subprocess.Popen([
        sys.executable, '-u', str(Path(__file__).with_name('catalog.py')),
        str(artists), '--work', str(work), '--cache', str(root/'work/catalog_run/cache'), '--deep',
    ], cwd=root, stdout=log, stderr=subprocess.STDOUT)
    last = None
    while True:
        deep_path = work/'deep.json'
        if deep_path.exists():
            current = deep_path.stat().st_mtime_ns
            if current != last:
                deep = json.loads(deep_path.read_text(encoding='utf-8'))
                combined = dict(regular)
                for name, result in deep.items():
                    old = regular.get(name, {'tracks': [], 'attempts': []})
                    combined[name] = {
                        'tracks': list(dict.fromkeys(tuple(r) for r in old['tracks'] + result['tracks'])),
                        'attempts': ['initial:' + a for a in old['attempts']] + ['deep:' + a for a in result['attempts']],
                    }
                try:
                    songs = export(target, combined)
                except OSError as exc:
                    print('Export temporarily blocked:', exc, flush=True)
                    time.sleep(10)
                    continue
                status = {'planned_artists': total, 'initial_completed': len(regular),
                          'deep_attempted': len(deep), 'unique_candidate_songs': songs,
                          'deep_process_running': process.poll() is None}
                temp = target/'deep_summary.tmp'
                temp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
                replace_file(temp, target/'deep_summary.json')
                last = current
                print(json.dumps(status), flush=True)
        if process.poll() is not None:
            print('Deep query process exited', process.returncode, flush=True)
            break
        time.sleep(10)
