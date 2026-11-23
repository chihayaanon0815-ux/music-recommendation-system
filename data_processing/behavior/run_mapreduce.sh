#!/usr/bin/env bash
set -euo pipefail

# Hadoop Streaming 本地模式（LocalJobRunner）跑 48,373,586 行统计
# 环境：WSL Ubuntu，Java 11，Hadoop 3.3.6

DIST=/mnt/d/DSH-Work/dist/hadoop-3.3.6.tar.gz
SRC_DATA=/mnt/d/DSH-Work/msd/train_triplets.txt
WORK=/mnt/d/DSH-Work/music_meta/mr
HADOOP_DIR="$HOME/hadoop-3.3.6"

export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(which java)")")")"
export HADOOP_HOME="$HOME/hadoop-3.3.6"
export PATH="$HADOOP_HOME/bin:$PATH"

if [ ! -d "$HADOOP_DIR" ]; then
  echo "[setup] extracting hadoop ..."
  mkdir -p "$HOME/hadoop_extract"
  tar -xzf "$DIST" -C "$HOME/hadoop_extract"
  mv "$HOME/hadoop_extract/hadoop-3.3.6" "$HADOOP_DIR"
  rmdir "$HOME/hadoop_extract"
fi

# 本地模式配置：fs.defaultFS=file:///，mapreduce.framework.name=local
mkdir -p "$HADOOP_HOME/etc/hadoop"
cat > "$HADOOP_HOME/etc/hadoop/core-site.xml" <<'EOF'
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>file:///</value></property>
</configuration>
EOF
cat > "$HADOOP_HOME/etc/hadoop/mapred-site.xml" <<'EOF'
<?xml version="1.0"?>
<configuration>
  <property><name>mapreduce.framework.name</name><value>local</value></property>
</configuration>
EOF

grep -q 'export JAVA_HOME' "$HADOOP_HOME/etc/hadoop/hadoop-env.sh" || \
  echo "export JAVA_HOME=$JAVA_HOME" >> "$HADOOP_HOME/etc/hadoop/hadoop-env.sh"

echo "[check] hadoop version:"
hadoop version | head -2

mkdir -p "$HOME/data"
if [ ! -f "$HOME/data/train_triplets.txt" ]; then
  echo "[setup] copying 3GB triplets into WSL fs ..."
  cp "$SRC_DATA" "$HOME/data/train_triplets.txt"
fi
cp "$WORK/mapper.py" "$WORK/reducer.py" "$HOME/data/"

rm -rf "$HOME/data/mr_out"
START=$(date +%s)
echo "[run] hadoop streaming job start ..."
hadoop jar "$HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-3.3.6.jar" \
  -D mapreduce.framework.name=local \
  -D mapreduce.input.fileinputformat.split.maxsize=268435456 \
  -D mapreduce.job.reduces=4 \
  -files "$HOME/data/mapper.py,$HOME/data/reducer.py" \
  -mapper "python3 mapper.py" \
  -reducer "python3 reducer.py" \
  -input "file://$HOME/data/train_triplets.txt" \
  -output "file://$HOME/data/mr_out"
END=$(date +%s)
ELAPSED=$((END - START))
echo "[run] done in ${ELAPSED}s"

mkdir -p "$WORK/out"
rm -f "$WORK/out/"part-*
cp "$HOME/data/mr_out/part-"* "$WORK/out/" 2>/dev/null || true

python3 - "$WORK/out" "$ELAPSED" "$WORK/mapreduce_metrics.json" <<'PY'
import glob, json, os, sys

out_dir, elapsed, dest = sys.argv[1], int(sys.argv[2]), sys.argv[3]
rows = 0
plays = 0
users = 0
per_song = {}
for path in glob.glob(os.path.join(out_dir, "part-*")):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            sid, u, p = line.split(",")
            rows += 1
            users += int(u)
            plays += int(p)
            per_song[sid] = (int(u), int(p))

with open(os.path.join(os.path.dirname(out_dir), "song_stats.csv"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("song_id,users,plays\n")
    for sid in sorted(per_song):
        u, p = per_song[sid]
        fh.write(f"{sid},{u},{p}\n")

metrics = {
    "engine": "Hadoop Streaming 3.3.6 (LocalJobRunner, 单机本地模式)",
    "input_rows": 48373586,
    "input_file": "train_triplets.txt (3.0 GB)",
    "songs": rows,
    "sum_users": users,
    "sum_plays": plays,
    "elapsed_seconds": elapsed,
    "split_maxsize_mb": 256,
    "reducers": 4,
    "java": "OpenJDK 11 (WSL Ubuntu)",
    "note": "LocalJobRunner 单机执行，仅作 MapReduce 编程模型对比，不代表多节点集群性能；未使用 HDFS/YARN。",
}
with open(dest, "w", encoding="utf-8") as fh:
    json.dump(metrics, fh, ensure_ascii=False, indent=2)
print(json.dumps(metrics, ensure_ascii=False, indent=2))
PY

echo "[done] output copied to $WORK"
