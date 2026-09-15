"""CSV -> SQLite. Usage: py load.py "C:\\path\\buiding_all.csv" """
import csv, sqlite3, sys, os

CSV = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\91999\Downloads\buiding_all.csv"
DB = os.path.join(os.path.dirname(__file__), "reviews.db")

def main():
    with open(CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    db = sqlite3.connect(DB)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS buildings (
        id TEXT PRIMARY KEY, name TEXT, locality TEXT,
        lat REAL, lng REAL, map_link TEXT
    );
    CREATE TABLE IF NOT EXISTS places (
        building_id TEXT PRIMARY KEY REFERENCES buildings(id),
        place_id TEXT, returned_name TEXT,
        distance_m REAL, status TEXT, resolved_at TEXT
    );
    CREATE TABLE IF NOT EXISTS reviews (
        review_id TEXT PRIMARY KEY, building_id TEXT REFERENCES buildings(id),
        rating INTEGER, text TEXT, review_time TEXT, lang TEXT,
        author_hash TEXT, owner_response TEXT, fetched_at TEXT
    );
    """)

    def num(v):
        v = (v or "").strip()
        try: return float(v)
        except ValueError: return None

    n = 0
    for r in rows:
        bid = (r.get("id") or "").strip()
        name = (r.get("name") or "").strip()
        if not bid or not name or (r.get("deletedAt") or "").strip():
            continue
        db.execute(
            "INSERT INTO buildings(id,name,locality,lat,lng,map_link) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, locality=excluded.locality, "
            "lat=excluded.lat, lng=excluded.lng, map_link=excluded.map_link",
            (bid, name, (r.get("locality") or "").strip(),
             num(r.get("latitude")), num(r.get("longitude")),
             (r.get("mapLink") or "").strip()),
        )
        n += 1
    db.commit()
    total, with_coords = db.execute(
        "SELECT COUNT(*), COUNT(lat) FROM buildings").fetchone()
    print(f"loaded {n} rows -> {DB}")
    print(f"buildings: {total}, with coords: {with_coords}")
    db.close()

if __name__ == "__main__":
    main()
