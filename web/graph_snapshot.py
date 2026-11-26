"""Assemble and verify the graph index distributed with the catalog."""

import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from web.catalog_snapshot import materialize


def file_sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def restore_published_index(data):
    manifest_path = data / "graph_index_snapshot.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    songs = data / "songs.csv"
    materialize(songs)
    if file_sha256(songs) != manifest["source_sha256"]:
        raise ValueError("歌曲 CSV 与发布的图索引版本不一致")
    index = data / "graph_index.sqlite3"
    if index.is_file() and file_sha256(index) == manifest["index_sha256"]:
        return

    scratch = None
    folder = (data / "graph-index-parts").resolve()
    try:
        with tempfile.NamedTemporaryFile(dir=data, delete=False) as output:
            scratch = Path(output.name)
            for entry in manifest["parts"]:
                part = (folder / entry["file"]).resolve()
                if part.parent != folder:
                    raise ValueError("图索引分片路径无效")
                compressed = part.read_bytes()
                if hashlib.sha256(compressed).hexdigest() != entry["sha256"]:
                    raise ValueError(f"图索引分片校验失败：{part.name}")
                with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as block:
                    shutil.copyfileobj(block, output)
        if scratch.stat().st_size != manifest["index_bytes"] or file_sha256(scratch) != manifest["index_sha256"]:
            raise ValueError("还原后的图索引校验失败")
        os.replace(scratch, index)
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)
