"""Resolve and export the versioned catalog when it is stored in CSV parts."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def catalog_paths(path):
    if path.is_file() or path.name != 'songs.csv':
        return (path,)
    manifest = path.with_name('catalog_snapshot.json')
    if not manifest.is_file():
        return (path,)
    entries = json.loads(manifest.read_text(encoding='utf-8'))['files']
    root = manifest.resolve().parents[2]
    parts = tuple((root / entry['path']).resolve() for entry in entries)
    folder = path.parent.resolve()
    if not parts or any(not item.is_relative_to(folder) for item in parts):
        raise ValueError('曲库分片路径无效')
    return parts


def materialize(path):
    if path.is_file():
        return
    parts = catalog_paths(path)
    manifest = json.loads(path.with_name('catalog_snapshot.json').read_text(encoding='utf-8'))
    scratch = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
            scratch = Path(out.name)
            header = None
            for part, entry in zip(parts, manifest['files'], strict=True):
                with part.open('rb') as content:
                    if hashlib.file_digest(content, 'sha256').hexdigest() != entry['sha256']:
                        raise ValueError(f'曲库分片校验失败：{part.name}')
                    content.seek(0)
                    actual = content.readline()
                    if header is None:
                        header = actual
                        out.write(header)
                    elif actual != header:
                        raise ValueError(f'曲库分片表头不一致：{part.name}')
                    shutil.copyfileobj(content, out)
        with scratch.open('rb') as merged:
            if hashlib.file_digest(merged, 'sha256').hexdigest() != manifest['songs_sha256']:
                raise ValueError('合并后的曲库校验失败')
        os.replace(scratch, path)
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)


if __name__ == '__main__':
    materialize(Path(__file__).resolve().parents[1] / 'data/processed/songs.csv')
