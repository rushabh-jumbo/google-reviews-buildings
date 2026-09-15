#!/usr/bin/env bash
# Launch N resolver shards in parallel. Usage: ./run_shards.sh 8
set -euo pipefail
N=${1:-8}
mkdir -p logs
for i in $(seq 0 $((N-1))); do
  nohup python3 resolve.py --shard "$i/$N" > "logs/shard_$i.log" 2>&1 &
  echo "started shard $i/$N (pid $!)"
done
wait
python3 merge.py
