"""Fold every places_*.db shard into reviews.db. Safe to rerun."""
import sqlite3, glob, os

HERE = os.path.dirname(os.path.abspath(__file__))
main = sqlite3.connect(os.path.join(HERE, "reviews.db"))
main.execute("""CREATE TABLE IF NOT EXISTS places (
    building_id TEXT PRIMARY KEY, place_id TEXT, returned_name TEXT,
    distance_m REAL, status TEXT, resolved_at TEXT,
    rating REAL, review_count INTEGER)""")
for col in ("rating REAL", "review_count INTEGER"):
    try:
        main.execute(f"ALTER TABLE places ADD COLUMN {col}")
    except sqlite3.OperationalError:
        pass

n = 0
for f in sorted(glob.glob(os.path.join(HERE, "places_*.db"))):
    s = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
    cols = len([c for c in s.execute("PRAGMA table_info(places)")])
    q = "INSERT OR REPLACE INTO places VALUES(" + ",".join("?" * cols) + ")"
    for row in s.execute("SELECT * FROM places"):
        main.execute(q, row)
        n += 1
    s.close()
main.commit()
for s, c in main.execute(
        "SELECT CASE WHEN status LIKE 'error%' THEN 'error' ELSE status END, "
        "COUNT(*) FROM places GROUP BY 1"):
    print(f"{s}: {c}")
print(f"merged {n} rows from shards")
