"""Dry-run: resolve building name -> Google place via the keyless Maps search
endpoint, verify with coordinate distance. Usage: py resolve_probe.py [limit]
"""
import sqlite3, sys, os, re, time, json, math, urllib.parse, urllib.request

DB = os.path.join(os.path.dirname(__file__), "reviews.db")
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 20
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
RESULT = re.compile(
    r'\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\],"(0x[0-9a-f]+:0x[0-9a-f]+)","([^"]+)"')

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
    m = re.search(r'href="(/search\?tbm=map[^"]+)"', h)
    if not m:
        return None
    d = get("https://www.google.com" + urllib.parse.unquote(m.group(1)).replace("&amp;", "&"))
    r = RESULT.search(d[d.find("["):])
    if not r:
        return None
    return {"lat": float(r.group(1)), "lng": float(r.group(2)),
            "place_ref": r.group(3), "returned_name": r.group(4)}

def main():
    db = sqlite3.connect(DB)
    rows = db.execute("SELECT id,name,locality,lat,lng FROM buildings "
                      "WHERE lat IS NOT NULL ORDER BY id LIMIT ?", (LIMIT,)).fetchall()
    out = []
    for bid, name, loc, lat, lng in rows:
        q = ", ".join(x for x in (name, loc, "Bengaluru") if x)
        try:
            p = resolve(q)
        except Exception as e:
            p = None
            err = str(e)
        rec = {"id": bid, "query": q}
        if p:
            dist = round(haversine(lat, lng, p["lat"], p["lng"]))
            rec.update(returned_name=p["returned_name"], place_ref=p["place_ref"],
                       distance_m=dist,
                       verdict="ACCEPT" if dist < 200 else "REVIEW")
        else:
            rec.update(verdict="NO_MATCH")
        out.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        time.sleep(2)
    acc = sum(r["verdict"] == "ACCEPT" for r in out)
    rev = sum(r["verdict"] == "REVIEW" for r in out)
    nm = sum(r["verdict"] == "NO_MATCH" for r in out)
    print(f"\nACCEPT {acc} / REVIEW {rev} / NO_MATCH {nm}  (of {len(out)})")
    with open(os.path.join(os.path.dirname(__file__), "probe_result.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
