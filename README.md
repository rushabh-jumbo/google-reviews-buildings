# Google Reviews for Jumbo buildings

Pipeline: **load buildings → resolve each to a Google place (CID) → scrape reviews → categorise.**
Steps 1–3 are built. Categorisation is next.

## If you're an agent picking this up fresh

Read this whole file before touching anything, then note:

- **Never run `python3 resolve.py` or `python3 run_scrape.py` with no arguments
  "just to test something."** No-args means "process every remaining
  building" — thousands of them. Always pass `--limit N` for a smoke test.
  I made this mistake twice in-session and had to kill the job.
- `resolve.py`'s `RATING` regex (captures rating + review count for free from
  the same response) is best-effort and occasionally misses on a re-request
  to the identical URL for no clear reason — don't over-invest in debugging
  it further, `run_scrape.py` already treats a missing count as "skip the
  retry-on-shortfall check, trust the first attempt."
- `scraper_pro/config.runner.yaml` must have **no `businesses` key** — if one
  exists, scraper_pro silently ignores the `--url` CLI flag and rescrapes
  whatever's in the config instead. This cost real debugging time to find.
- On Windows, both `resolve.py` and any subprocess call into `scraper_pro`
  need `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` (or `sys.stdout.reconfigure`)
  — the default console codepage crashes on em-dashes in building names and
  on scraper_pro's own progress-bar spinner glyphs. `run_scrape.py` already
  sets this via `ENV` for its subprocess calls.
- I validated a plain Playwright/Selenium scraper does **not** work — Google
  serves it a page with no Reviews tab at all, headless or headed, even with
  `navigator.webdriver` spoofed. Don't rebuild that path; it's a dead end
  already explored (see conversation history / git blame if available).
- `.db` files are excluded from any bundle/zip of this project — regenerate
  `reviews.db` via `load.py` against the source CSV.

Zero-cost throughout, but step 3 needs a real, undetected browser — the free
JSON endpoint (`listugcposts`) is 403'd, and even plain Playwright/Selenium
gets served a stripped page with no Reviews tab at all (Google detects the
automation regardless of headless/headed). `scraper_pro`
(SeleniumBase UC Mode) is the one that gets past it — confirmed empirically,
see step 3.

## Setup (VPS)

```bash
sudo apt install -y python3          # stdlib only, no pip packages
python3 load.py building_all.csv     # CSV -> reviews.db  (buildings table)
```

`load.py` takes the CSV path as arg 1. It skips deleted / unnamed rows and
rows without coordinates.

## Step 2 — resolve buildings to Google places

Single process (~2.5 s/building, ~8 h for 11k):

```bash
python3 resolve.py
```

Parallel across N workers (recommended on a VPS — put them behind different
egress IPs / proxies if you can, Google rate-limits per IP):

```bash
./run_shards.sh 8        # 8 shards + auto-merge at the end
```

- Each shard only touches buildings where `crc32(id) % N == shard_index`, so
  workers need **no coordination** and can run on separate machines.
- Shard `i` writes `places_i.db`. `merge.py` folds them all into `reviews.db`.
- Fully **resumable** — rerun any shard and it skips what's already done
  (checks both its own `places_i.db` and the shared `reviews.db`).
- Rate-limit handling: on a Google `/sorry/` page the shard sleeps with
  exponential backoff (up to ~64 min) and retries. If a whole shard is stuck
  in backoff, that IP is burnt — move it to another IP/proxy.

Tune in `resolve.py`: `ACCEPT_M` (200 m match threshold), the `time.sleep`
between requests, `UA`.

### Output: `places` table

| column | meaning |
|---|---|
| `building_id` | FK to `buildings.id` |
| `place_id` | Google CID, form `0x…:0x…` (feed this to the review scraper) |
| `returned_name` | name Google resolved to — eyeball against `buildings.name` |
| `distance_m` | metres between CSV coords and the resolved place |
| `status` | `accept` (<200 m), `review` (further — check by hand), `no_match`, `error:…` |

QA the `review` bucket:

```bash
sqlite3 -header -csv reviews.db \
 "SELECT b.name, p.returned_name, p.distance_m, b.map_link
  FROM places p JOIN buildings b ON b.id=p.building_id
  WHERE p.status='review' ORDER BY p.distance_m" > qa_review.csv
```

## Step 3 — scrape reviews

Uses `scraper_pro/` (vendored: `github.com/georgekhananaev/google-reviews-scraper-pro`,
MIT, SeleniumBase UC Mode). Setup once:

```bash
cd scraper_pro && pip install -r requirements.txt
```

Then from the project root:

```bash
python3 run_scrape.py                # single process
./run_scrape_shards.sh 4             # 4 parallel Chrome instances + auto-import
```

- Each shard drives real Chrome one building at a time via `scraper_pro`'s
  CLI (`--url "maps?cid=..."`), pointed at `scraper_pro/config.runner.yaml`
  (a config with **no** `businesses` list — required, otherwise scraper_pro
  silently prefers its config's business list over `--url`).
- **Retry-on-shortfall**: the "sort by newest" click inside scraper_pro
  occasionally races and the scrape then stalls after ~5 reviews instead of
  the true count. `run_scrape.py` compares what it got against the
  `review_count` resolve.py already captured (free, from the same response
  used to resolve the place) and retries up to 3× when short. Confirmed this
  actually fixes it: a stuck 5/375 became a clean 375/375 on retry.
- Progress lives in `reviews.db`'s `scrape_status` table (`ok` / `partial`
  after exhausting retries), so reruns are resumable and shard-safe.
- Each shard writes into its own `scraper_pro/shard_i.db` (scraper_pro's own
  schema) — `import_scraper_reviews.py` folds every shard into `reviews.db`'s
  `reviews` table, matching by CID back to `building_id`.
- Cost: ~15–60s/building (real browser, not a raw HTTP call). Budget several
  days across a handful of shards for the full 11k; RAM is the limit, not CPU
  (~300–400MB per Chrome instance).
- `--limit N` on `run_scrape.py` caps how many buildings a run touches — use
  it to smoke-test before committing to a big shard.
- Buildings resolved *before* this `review_count` column existed have it as
  `NULL` — those get a single best-effort attempt (no retry-on-shortfall,
  since there's nothing to compare against). Rerun `resolve.py` on them
  (reset their `places.status` to anything starting with `error`) to backfill
  the count if you want retry protection on the whole set.

## Files

- `load.py` — CSV → SQLite
- `resolve.py` — building → Google place (+ rating/review_count), shardable, resumable
- `run_shards.sh` — launch N resolve shards + merge
- `merge.py` — fold `places_*.db` → `reviews.db`
- `resolve_probe.py` — 20-row dry run, prints verdicts (no DB writes to `places`)
- `scraper_pro/` — vendored review scraper (see step 3)
- `run_scrape.py` — orchestrates scraper_pro per building, with retry-on-shortfall
- `run_scrape_shards.sh` — launch N scrape shards + auto-import
- `import_scraper_reviews.py` — fold scraper_pro shard DBs → `reviews.db`
- `seed_reviews.py` — hand-collected proof-of-concept reviews for 4 buildings (safe to ignore/delete)
