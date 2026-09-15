"""Resolve buildings -> Google place (CID), verified by coordinate distance.
Keyless: scrapes the Google Maps search endpoint. Resumable. Shardable.

  py resolve.py                       # single process, writes into reviews.db
  py resolve.py --shard 0/4           # worker 0 of 4, writes places_0.db
  py resolve.py --shard 1/4           # worker 1 of 4, writes places_1.db  ...
  py merge.py                         # fold places_*.db back into reviews.db

Each shard only touches buildings where crc32(id) %% N == i, so workers need
no coordination and can run on separate machines/IPs. Source building rows are
read from reviews.db (read-only, safe to share); run load.py there first.
"""
import sqlite3, sys, os, re, time, math, random, zlib, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # avoid Windows cp1252 crashes on em-dash names

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DB = os.path.join(HERE, "reviews.db")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
RESULT = re.compile(
    r'\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\],"(0x[0-9a-f]+:0x[0-9a-f]+)","([^"]+)"')
RATING = re.compile(r'(\d\.\d),(\d+)\],null,null,null,null,\[null,null,-?\d+\.\d+,-?\d+\.\d+\],"0x[0-9a-f]+:0x[0-9a-f]+"')
ACCEPT_M = 200

SHARD_I, SHARD_N = 0, 1
if "--shard" in sys.argv:
    SHARD_I, SHARD_N = (int(x) for x in sys.argv[sys.argv.index("--shard") + 1].split("/"))
assert 0 <= SHARD_I < SHARD_N, "--shard i/n needs 0 <= i < n"

OUT_DB = os.path.join(HERE, f"places_{SHARD_I}.db" if SHARD_N > 1 else "reviews.db")

def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Cookie": "CONSENT=YES+cb"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")

def haversine(a, b, c, d):
    R = 6371000
    p1, p2, dp, dl = math.radians(a), math.radians(c), math.radians(c-a), math.radians(d-b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))

def resolve(q):
    h = get("https://www.google.com/maps/search/" + urllib.parse.quote(q) + "?hl=en&gl=in")
    if "/sorry/" in h or "unusual traffic" in h:
        raise RuntimeError("rate-limited")
    m = re.search(r'href="(/search\?tbm=map[^"]+)"', h)
    if not m:
        return None
    d = get("https://www.google.com" + urllib.parse.unquote(m.group(1)).replace("&amp;", "&"))
    if "/sorry/" in d:
        raise RuntimeError("rate-limited")
    body = d[d.find("["):]
    r = RESULT.search(body)
    if not r:
        return None
    rt = RATING.search(body)
    return {"lat": float(r.group(1)), "lng": float(r.group(2)),
            "place_ref": r.group(3), "returned_name": r.group(4),
            "rating": float(rt.group(1)) if rt else None,
            "review_count": int(rt.group(2)) if rt else None}

def main():
    src = sqlite3.connect(f"file:{SRC_DB}?mode=ro", uri=True, timeout=30)
    out = sqlite3.connect(OUT_DB, timeout=30)
    out.execute("""CREATE TABLE IF NOT EXISTS places (
        building_id TEXT PRIMARY KEY, place_id TEXT, returned_name TEXT,
        distance_m REAL, status TEXT, resolved_at TEXT,
        rating REAL, review_count INTEGER)""")
    for col in ("rating REAL", "review_count INTEGER"):  # widen tables from before this field existed
        try:
            out.execute(f"ALTER TABLE places ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    # "seen" = permanently resolved; transient errors are retried on rerun,
    # not treated as done.
    seen = {r[0] for r in out.execute(
        "SELECT building_id FROM places WHERE status NOT LIKE 'error%'")}
    try:  # also skip anything already resolved in the shared reviews.db
        seen |= {r[0] for r in src.execute(
            "SELECT building_id FROM places WHERE status NOT LIKE 'error%'")}
    except sqlite3.OperationalError:
        pass

    rows = [r for r in src.execute(
                "SELECT id,name,locality,lat,lng FROM buildings WHERE lat IS NOT NULL")
            if zlib.crc32(r[0].encode()) % SHARD_N == SHARD_I and r[0] not in seen]
    print(f"shard {SHARD_I}/{SHARD_N}: {len(rows)} buildings to do -> {OUT_DB}")

    done = backoff = 0
    for bid, name, loc, lat, lng in rows:
        q = ", ".join(x for x in (name, loc, "Bengaluru") if x)
        try:
            p = resolve(q); backoff = 0
        except RuntimeError:
            backoff = min(backoff + 1, 6); wait = 60 * 2 ** backoff
            print(f"  rate-limited, sleeping {wait}s"); time.sleep(wait); continue
        except Exception as e:
            p = {"_err": str(e)[:120]}
        now = datetime.now(timezone.utc).isoformat()
        if not p:
            row = (bid, None, None, None, "no_match", now, None, None)
        elif "_err" in p:
            row = (bid, None, None, None, "error:" + p["_err"], now, None, None)
        else:
            dist = haversine(lat, lng, p["lat"], p["lng"])
            row = (bid, p["place_ref"], p["returned_name"], round(dist),
                   "accept" if dist < ACCEPT_M else "review", now,
                   p["rating"], p["review_count"])
        out.execute("INSERT OR REPLACE INTO places VALUES(?,?,?,?,?,?,?,?)", row)
        out.commit()
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(rows)}")
        time.sleep(1.5 + random.random())

    for s, c in out.execute(
            "SELECT CASE WHEN status LIKE 'error%' THEN 'error' ELSE status END, "
            "COUNT(*) FROM places GROUP BY 1"):
        print(f"{s}: {c}")

if __name__ == "__main__":
    main()
