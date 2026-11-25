"""Merge the researched covers into covers.json. A finding is used only when it has a URL from the
iTunes or Deezer image hosts, is not low confidence, and either is an exact-song match or the song had no cover."""
import json, sys
from pathlib import Path
from urllib.parse import urlparse

covers_p, research_p = Path(sys.argv[1]), Path(sys.argv[2])
covers = json.loads(covers_p.read_text(encoding="utf-8"))
research = json.loads(research_p.read_text(encoding="utf-8"))
ALLOWED = ("mzstatic.com", "dzcdn.net", "deezer.com")
used, skipped = [], []
for sid, r in research.items():
    url = (r or {}).get("art_url")
    host = urlparse(url).hostname or "" if url else ""
    old = covers.get(sid) or {}
    if not url or not host.endswith(ALLOWED):
        skipped.append((sid, "no url" if not url else f"host {host}")); continue
    if r.get("confidence") == "low":
        skipped.append((sid, "low confidence: " + (r.get("note") or "")[:80])); continue
    had_song = old.get("match") == "song" and old.get("art")
    if had_song and r.get("match") != "song":
        skipped.append((sid, "already has an exact cover")); continue
    covers[sid] = {"match": r.get("match") or "artist", "country": r.get("source"), "artist": old.get("artist") or r.get("artist"),
                   "title": old.get("title") or r.get("title"), "found_track": r.get("found_track"), "found_artist": r.get("found_artist"),
                   "album": r.get("album"), "art": url}
    used.append((sid, r.get("match"), r.get("confidence"), r.get("found_artist"), r.get("found_track")))
covers_p.write_text(json.dumps(covers, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"used {len(used)}, skipped {len(skipped)}")
for u in used: print("  use", *u)
for s in skipped: print("  skip", *s)
