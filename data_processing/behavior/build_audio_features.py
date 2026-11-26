# -*- coding: utf-8 -*-
"""Stage 5: 从 msd_summary_file.h5 抽取音频特征 + 歌手热度/知名度，补进元数据与维表。

重要发现：msd_summary_file.h5 的 danceability / energy 两列在全部 100 万行里都是 0
（不是缺失，是源文件未填充），因此不导出、不参与任何建模；其余特征（tempo/loudness/
key/mode/time_signature/song_hotttnesss/familiarity/hotttnesss）可用。

输入:
  D:\\DSH-Work\\msd\\msd_summary_file.h5（1,000,000 行，三张表按行对齐）
  cf_data\\msd_song_meta.csv, song_dim_kcore.csv, song_pool_named.csv

输出:
  cf_data\\msd_audio_features.csv   384,546 首的音频特征（按代表 track_id）
  cf_data\\msd_song_meta.csv        增加 artist_familiarity/hotttnesss/mbid/location/lat/lon
  cf_data\\song_dim_kcore.csv       增加热度与关键音频特征
  cf_data\\song_pool_named.csv      增加 song_hotttnesss/artist_hotttnesss
  cf_data\\msd_features_stats.json  覆盖与字段统计
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r"D:\DSH-Work\pyh5")
import h5py  # noqa: E402

H5 = r"D:\DSH-Work\msd\msd_summary_file.h5"
CF = r"D:\desktop\音乐推荐数据\cf_data"

META_NEW = ["artist_familiarity", "artist_hotttnesss", "artist_mbid",
            "artist_location", "artist_latitude", "artist_longitude"]
DIM_NEW = ["song_hotttnesss", "artist_familiarity", "artist_hotttnesss",
           "tempo", "loudness", "key", "mode", "time_signature"]
POOL_NEW = ["song_hotttnesss", "artist_hotttnesss"]


def dec(arr):
    return [x.decode("utf-8", "replace") if isinstance(x, (bytes, bytearray)) else str(x) for x in arr]


meta = pd.read_csv(os.path.join(CF, "msd_song_meta.csv"),
                   dtype={"song_id": str, "track_id": str}, keep_default_na=False)
meta = meta.drop(columns=[c for c in META_NEW if c in meta.columns])
print("meta rows:", len(meta), flush=True)

with h5py.File(H5, "r") as f:
    tracks = f["analysis/songs"]["track_id"][:].astype(str)
    idx = np.flatnonzero(np.isin(tracks, meta["track_id"].tolist()))
    print("matched tracks:", len(idx), "/", len(meta), flush=True)

    a = f["analysis/songs"][idx]
    m = f["metadata/songs"][idx]
    mb = f["musicbrainz/songs"][idx]

feat = pd.DataFrame({
    "track_id": a["track_id"].astype(str),
    "song_id": m["song_id"].astype(str),
    "audio_duration": a["duration"].astype(float),
    "key": a["key"].astype(int),
    "key_confidence": a["key_confidence"].astype(float),
    "loudness": a["loudness"].astype(float),
    "mode": a["mode"].astype(int),
    "mode_confidence": a["mode_confidence"].astype(float),
    "tempo": a["tempo"].astype(float),
    "time_signature": a["time_signature"].astype(int),
    "time_signature_confidence": a["time_signature_confidence"].astype(float),
    "end_of_fade_in": a["end_of_fade_in"].astype(float),
    "start_of_fade_out": a["start_of_fade_out"].astype(float),
    "song_hotttnesss": m["song_hotttnesss"].astype(float),
    "year_mb": mb["year"].astype(int),
    "artist_familiarity": m["artist_familiarity"].astype(float),
    "artist_hotttnesss": m["artist_hotttnesss"].astype(float),
    "artist_mbid": dec(m["artist_mbid"]),
    "artist_location": dec(m["artist_location"]),
    "artist_latitude": m["artist_latitude"].astype(float),
    "artist_longitude": m["artist_longitude"].astype(float),
})
print("feature frame:", feat.shape, flush=True)

chk = meta.set_index("track_id")["song_id"]
bad = int((feat["song_id"] != feat["track_id"].map(chk)).sum())
print("alignment mismatches:", bad, flush=True)

feat["year_mb"] = feat["year_mb"].where(feat["year_mb"] > 0, "")

audio_cols = ["track_id", "song_id", "audio_duration", "key", "key_confidence",
              "loudness", "mode", "mode_confidence", "tempo", "time_signature",
              "time_signature_confidence", "end_of_fade_in", "start_of_fade_out",
              "song_hotttnesss", "year_mb"]
feat[audio_cols].to_csv(os.path.join(CF, "msd_audio_features.csv"), index=False, encoding="utf-8")
print("wrote msd_audio_features.csv", flush=True)

meta = meta.merge(feat[["track_id"] + META_NEW], on="track_id", how="left")
meta.to_csv(os.path.join(CF, "msd_song_meta.csv"), index=False, encoding="utf-8")
print("enriched msd_song_meta.csv", meta.shape, flush=True)

dim = pd.read_csv(os.path.join(CF, "song_dim_kcore.csv"), dtype={"song_id": str}, keep_default_na=False)
dim = dim.drop(columns=[c for c in DIM_NEW + ["danceability", "energy"] if c in dim.columns])
dim = dim.merge(feat[["song_id"] + DIM_NEW], on="song_id", how="left")
dim.to_csv(os.path.join(CF, "song_dim_kcore.csv"), index=False, encoding="utf-8")
print("enriched song_dim_kcore.csv", dim.shape, flush=True)

pool = pd.read_csv(os.path.join(CF, "song_pool_named.csv"), dtype={"song_id": str}, keep_default_na=False)
pool = pool.drop(columns=[c for c in POOL_NEW + ["danceability", "energy"] if c in pool.columns])
pool = pool.merge(feat[["song_id"] + POOL_NEW], on="song_id", how="left")
pool.to_csv(os.path.join(CF, "song_pool_named.csv"), index=False, encoding="utf-8")
print("enriched song_pool_named.csv", pool.shape, flush=True)


def stats(series):
    s = pd.to_numeric(series, errors="coerce")
    return {
        "non_null": int(s.notna().sum()),
        "min": round(float(s.min()), 3) if s.notna().any() else None,
        "median": round(float(s.median()), 3) if s.notna().any() else None,
        "max": round(float(s.max()), 3) if s.notna().any() else None,
    }


out = {
    "behavior_songs": int(len(meta)),
    "tracks_matched_in_h5": int(len(feat)),
    "track_coverage_pct": round(len(feat) / len(meta) * 100, 2),
    "alignment_mismatches": bad,
    "unusable_fields": {
        "danceability": "源文件 1,000,000 行全为 0，未导出",
        "energy": "源文件 1,000,000 行全为 0，未导出",
    },
    "audio_features": {c: stats(feat[c]) for c in (
        "tempo", "loudness", "key", "mode", "time_signature",
        "song_hotttnesss", "artist_familiarity", "artist_hotttnesss")},
    "year_from_mb": {"non_empty": int((feat["year_mb"].astype(str) != "").sum()),
                     "pct": round((feat["year_mb"].astype(str) != "").sum() / len(feat) * 100, 2)},
    "artist_location_non_empty": int((feat["artist_location"] != "").sum()),
    "artist_mbid_non_empty": int((feat["artist_mbid"] != "").sum()),
    "source": "msd_summary_file.h5 (Echo Nest analysis/metadata/musicbrainz, 1,000,000 rows)",
}
with open(os.path.join(CF, "msd_features_stats.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
