# -*- coding: utf-8 -*-
"""核对 cf_data/文件清单与校验.txt：文件存在、大小一致、SHA-256 一致。"""
import hashlib
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
CF = os.path.join(BASE, "cf_data")
MANIFEST = os.path.join(CF, "文件清单与校验.txt")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(8 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    if not os.path.isfile(MANIFEST):
        print("missing manifest:", MANIFEST)
        return 1
    checked = missing = size_bad = hash_bad = 0
    problems = []
    for line in open(MANIFEST, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3:
            continue
        rel, size, expect = parts
        checked += 1
        path = os.path.join(CF, rel)
        if not os.path.isfile(path):
            missing += 1
            problems.append(f"missing {rel}")
            continue
        if os.path.getsize(path) != int(size):
            size_bad += 1
            problems.append(f"size mismatch {rel}")
        if sha256(path) != expect:
            hash_bad += 1
            problems.append(f"hash mismatch {rel}")
    print(f"checked={checked} missing={missing} size_mismatch={size_bad} hash_mismatch={hash_bad}")
    for p in problems[:20]:
        print(" -", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
