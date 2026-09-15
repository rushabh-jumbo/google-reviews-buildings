"""Fold every scraper_pro/shard_*.db into reviews.db's `reviews` table,
matching by CID (place_id prefix) back to building_id via our own places
table. Safe to rerun."""
import sqlite3, glob, os, json
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
main = sqlite3.connect(os.path.join(HERE, "reviews.db"))
main.execute("""CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY, building_id TEXT, rating INTEGER, text TEXT,
    review_time TEXT, lang TEXT, author_hash TEXT, owner_response TEXT,
    fetched_at TEXT)""")

prefix_to_building = {
    row[0].split(":")[0]: row[1]
    for row in main.execute(
        "SELECT place_id, building_id FROM places WHERE status = 'accept'")
}

n = skipped = 0
for f in sorted(glob.glob(os.path.join(HERE, "scraper_pro", "shard_*.db"))):
    s = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
    for row in s.execute("""SELECT review_id, place_id, author, rating, review_text,
                                    review_date, owner_responses
                             FROM reviews WHERE is_deleted = 0"""):
        rid, place_id, author, rating, text_json, review_date, owner_json = row
        bid = prefix_to_building.get(place_id.split(":")[0])
        if not bid:
            skipped += 1
            continue
        try:
            text = json.loads(text_json).get("en") or next(iter(json.loads(text_json).values()), "")
        except Exception:
            text = text_json or ""
        owner_resp = None
        try:
            ow = json.loads(owner_json) if owner_json else {}
            owner_resp = next(iter(ow.values()), None) if ow else None
        except Exception:
            pass
        main.execute("INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?,?,?,?)",
                     (rid, bid, rating, text, review_date, "en", author,
                      owner_resp, datetime.now(timezone.utc).isoformat()))
        n += 1
    s.close()
main.commit()
print(f"imported/updated {n} reviews, skipped {skipped} (place not in our accept set)")
print("reviews table total:", main.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])
