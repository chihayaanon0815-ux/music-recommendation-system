# -*- coding: utf-8 -*-
"""重新生成 cf_data/文件清单与校验.txt（跳过 .crc / _SUCCESS 等 Spark 元数据文件）。"""
import hashlib
import os

CF = r"D:\desktop\音乐推荐数据\cf_data"
OUT = os.path.join(CF, "文件清单与校验.txt")

SKIP_SUFFIX = (".crc",)
SKIP_NAMES = {"_SUCCESS", "文件清单与校验.txt"}


def sha256(path, chunk=8 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


rows = []
for root, dirs, names in os.walk(CF):
    dirs.sort()
    for nm in sorted(names):
        if nm in SKIP_NAMES or nm.endswith(SKIP_SUFFIX):
            continue
        path = os.path.join(root, nm)
        rel = os.path.relpath(path, CF).replace("\\", "/")
        rows.append((rel, os.path.getsize(path)))

lines = ["cf_data 文件清单与 SHA-256（2026-11-23 元数据补全后）", ""]
for rel, size in rows:
    lines.append(f"{rel}\t{size}\t{sha256(os.path.join(CF, rel))}")
lines.append("")
lines.append(f"文件数（不含 .crc/_SUCCESS）：{len(rows)}")
lines.append(f"合计字节：{sum(s for _, s in rows)}")
with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines) + "\n")
print("written", OUT, "files", len(rows), "bytes", sum(s for _, s in rows))
