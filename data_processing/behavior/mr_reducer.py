#!/usr/bin/env python3
"""Reducer: 聚合每首歌的用户数与播放次数，输出 song_id,users,plays。"""
import sys

cur = None
users = 0
plays = 0
for line in sys.stdin:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 3:
        continue
    song, kind, value = parts
    if song != cur:
        if cur is not None:
            sys.stdout.write(f"{cur},{users},{plays}\n")
        cur = song
        users = 0
        plays = 0
    if kind == "U":
        users += 1
    elif kind == "P":
        plays += int(value)
if cur is not None:
    sys.stdout.write(f"{cur},{users},{plays}\n")
