"""Look up album artwork URLs for each catalogue song through the public iTunes Search API.
Writes covers.json next to this script. Only metadata is fetched (no images)."""
import csv, json, sys, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

cat = Path(sys.argv[1])
out = Path(__file__).with_name("covers.json")
done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())

def search(term, country):
    q = urllib.parse.urlencode({"term": term, "media": "music", "entity": "song", "limit": 25, "country": country})
    req = urllib.request.Request("https://itunes.apple.com/search?" + q, headers={"User-Agent": "catalogue-lookup/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("results", [])
        except Exception as e:
            time.sleep(10 * (attempt + 1))
    return []

rows = list(csv.DictReader(cat.open(encoding="utf-8")))
for row in rows:
    sid = row["song_id"]
    if sid in done:
        continue
    artist, title = row["artist_name"], row["title"]
    best = None
    for country in ("cm", "fr", "us"):
        res = search(f"{artist} {title}", country)
        time.sleep(3)
        a, t = norm(artist), norm(title)
        same_artist = [x for x in res if a and a in norm(x.get("artistName"))]
        exact = [x for x in same_artist if t and (t in norm(x.get("trackName")) or norm(x.get("trackName")) in t)]
        pick = (exact or [None])[0]
        if pick:
            best = {"match": "song", "country": country}
        elif same_artist and not best:
            pick = same_artist[0]
            best = {"match": "artist", "country": country}
        if pick:
            best.update({
                "artist": artist, "title": title,
                "found_track": pick.get("trackName"), "found_artist": pick.get("artistName"),
                "album": pick.get("collectionName"),
                "art": (pick.get("artworkUrl100") or "").replace("100x100bb", "600x600bb"),
            })
            if best["match"] == "song":
                break
    done[sid] = best or {"match": "none", "artist": artist, "title": title}
    out.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    print(sid, done[sid]["match"], artist, "-", title, flush=True)
print("finished", len(done))
