"""Scrape reviews for every 'accept' building via scraper_pro (SeleniumBase UC
Mode — plain Playwright/Selenium gets served a page with no Reviews tab at
all, this is the tool that actually gets past it). Drives scraper_pro
one building at a time via its CLI and retries when a run stalls early
(a known flaky step: the "sort by newest" click occasionally races and the
scrape then stops after ~5 reviews instead of the true count).

Setup (once):
  cd scraper_pro && pip install -r requirements.txt

Usage:
  py run_scrape.py                    # single process
  py run_scrape.py --shard 0/8        # worker 0 of 8 -> scraper_pro/shard_0.db
  py import_scraper_reviews.py        # fold every shard's scraper_pro db into reviews.db
"""
import sqlite3, sys, os, subprocess, time, zlib, json
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRAPER_DIR = os.path.join(HERE, "scraper_pro")
SRC_DB = os.path.join(HERE, "reviews.db")
MAX_ATTEMPTS = 3
SHORTFALL_TOLERANCE = 0.9  # accept if we got >= 90% of the known review count
PER_BUILDING_TIMEOUT = 600  # seconds

SHARD_I, SHARD_N = 0, 1
if "--shard" in sys.argv:
    SHARD_I, SHARD_N = (int(x) for x in sys.argv[sys.argv.index("--shard") + 1].split("/"))
assert 0 <= SHARD_I < SHARD_N
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

SCRAPER_DB = os.path.join(SCRAPER_DIR, f"shard_{SHARD_I}.db" if SHARD_N > 1 else "shard_0.db")
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def cid_url(place_id):
    return f"https://www.google.com/maps?cid={int(place_id.split(':')[1], 16)}"


def scraped_count(place_id_prefix):
    # places.total_reviews is stale/unmaintained in scraper_pro - count reviews directly
    if not os.path.exists(SCRAPER_DB):
        return 0
    d = sqlite3.connect(SCRAPER_DB)
    row = d.execute(
        "SELECT COUNT(*) FROM reviews WHERE place_id LIKE ? AND is_deleted = 0",
        (place_id_prefix + ":%",)).fetchone()
    d.close()
    return row[0] if row else 0


def run_one(building_id, place_id):
    # config.runner.yaml has no "businesses" list - required for --url to be
    # honored, since a non-empty "businesses" in the config silently wins
    url = cid_url(place_id)
    subprocess.run(
        ["py", "start.py", "--config", "config.runner.yaml",
         "--url", url, "--scrape-mode", "full", "--db-path", SCRAPER_DB,
         "--custom-params", json.dumps({"building_id": building_id})],
        cwd=SCRAPER_DIR, env=ENV, timeout=PER_BUILDING_TIMEOUT, capture_output=True)
    return scraped_count(place_id.split(":")[0])


def main():
    src = sqlite3.connect(f"file:{SRC_DB}?mode=ro", uri=True, timeout=30)
    out = sqlite3.connect(SRC_DB, timeout=30)  # progress table lives in the shared db
    out.execute("""CREATE TABLE IF NOT EXISTS scrape_status (
        building_id TEXT PRIMARY KEY, place_id TEXT, scraped_count INTEGER,
        known_count INTEGER, attempts INTEGER, status TEXT, updated_at TEXT)""")

    done = {r[0] for r in out.execute(
        "SELECT building_id FROM scrape_status WHERE status = 'ok'")}

    rows = [r for r in src.execute("""
                SELECT b.id, p.place_id, p.review_count FROM buildings b
                JOIN places p ON p.building_id = b.id
                WHERE p.status = 'accept'""")
            if zlib.crc32(r[0].encode()) % SHARD_N == SHARD_I and r[0] not in done]
    if LIMIT:
        rows = rows[:LIMIT]
    print(f"shard {SHARD_I}/{SHARD_N}: {len(rows)} buildings to scrape")

    for n, (bid, place_id, known_count) in enumerate(rows, 1):
        got, attempts, status = 0, 0, "error"
        for attempts in range(1, MAX_ATTEMPTS + 1):
            try:
                got = run_one(bid, place_id)
            except subprocess.TimeoutExpired:
                got = scraped_count(place_id.split(":")[0])
            if known_count is None or got >= known_count * SHORTFALL_TOLERANCE:
                status = "ok"
                break
            print(f"  {bid}: got {got}/{known_count}, retrying ({attempts}/{MAX_ATTEMPTS})")
        else:
            status = "partial"  # exhausted retries, kept whatever we got
        out.execute("INSERT OR REPLACE INTO scrape_status VALUES(?,?,?,?,?,?,?)",
                   (bid, place_id, got, known_count, attempts, status,
                    datetime.now(timezone.utc).isoformat()))
        out.commit()
        if n % 10 == 0:
            print(f"  {n}/{len(rows)}")

    for s, c in out.execute("SELECT status, COUNT(*) FROM scrape_status GROUP BY status"):
        print(f"{s}: {c}")

if __name__ == "__main__":
    main()
