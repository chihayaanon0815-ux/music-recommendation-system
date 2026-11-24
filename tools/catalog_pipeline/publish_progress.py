"""Publish snapshots of the existing catalog run without making any requests."""
import csv
import argparse
import json
import time
from collections import Counter
from pathlib import Path

from catalog import export

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, default=root / 'work/catalog_run')
parser.add_argument('--output', type=Path, default=root / 'outputs/多来源采集-本轮结果')
parser.add_argument('--artists', type=Path, default=Path(__file__).with_name('artists.csv'))
args = parser.parse_args()
work = args.work
target = args.output
target.mkdir(exist_ok=True)
with args.artists.open(encoding='utf-8-sig', newline='') as file:
    regions = {row['候选名称'].strip(): row['覆盖规划'] for row in csv.DictReader(file)}

last_version = None
while True:
    progress = work / 'progress.json'
    version = progress.stat().st_mtime_ns
    states = json.loads(progress.read_text(encoding='utf-8'))
    if version != last_version:
        unique_count = export(target, states)
        matched = [name for name, data in states.items() if data['tracks']]
        summary = {
            'planned_artists': len(regions),
            'attempted_artists': len(states),
            'artists_with_results': len(matched),
            'unique_candidate_songs': unique_count,
            'attempted_by_region': dict(Counter(regions[name] for name in states)),
            'matched_by_region': dict(Counter(regions[name] for name in matched)),
        }
        temp = target / 'summary.tmp'
        temp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(target / 'summary.json')
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        last_version = version
    if len(states) >= len(regions):
        break
    time.sleep(10)
