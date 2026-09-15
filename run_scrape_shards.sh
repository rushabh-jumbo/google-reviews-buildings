#!/usr/bin/env bash
# Launch N review-scraping shards in parallel. Usage: ./run_scrape_shards.sh 4
# Fewer shards than run_shards.sh (resolve step) - each one is a real Chrome
# instance (~300-400MB RAM), not a raw HTTP call.
set -euo pipefail
N=${1:-4}
for i in $(seq 0 $((N-1))); do
  nohup python3 run_scrape.py --shard "$i/$N" > "scrape_shard_$i.log" 2>&1 &
  echo "started scrape shard $i/$N (pid $!)"
done
wait
python3 import_scraper_reviews.py
