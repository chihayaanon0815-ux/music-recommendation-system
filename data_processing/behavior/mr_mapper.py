#!/usr/bin/env python3
"""Mapper: 输出 (song_id, U, 1) 与 (song_id, P, play_count)。"""
import sys

for line in sys.stdin:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 3:
        continue
    _user, song, count = parts
    try:
        c = int(count)
    except ValueError:
        continue
    sys.stdout.write(f"{song}\tU\t1\n")
    sys.stdout.write(f"{song}\tP\t{c}\n")
