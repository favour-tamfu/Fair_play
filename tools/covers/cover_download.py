"""Download the album covers found by cover_lookup.py (approved by the user), shrink them to 300px WebP
and write web/assets/covers/index.json. Only covers whose found artist really is the catalogue artist are kept."""
import hashlib, json, re, subprocess, sys, time, unicodedata, urllib.request
from pathlib import Path

covers = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raw = Path(sys.argv[2]); raw.mkdir(parents=True, exist_ok=True)      # untrusted downloads, own folder
out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)      # web/assets/covers

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())

# Optional 4th argument: the catalogue CSV, whose artist_alias column lists other names of the same artist.
ALIASES = {}
if len(sys.argv) > 4:
    import csv
    for row in csv.DictReader(open(sys.argv[4], encoding="utf-8")):
        names = {norm(row["artist_name"])} | {norm(a) for a in (row.get("artist_alias") or "").split(";") if a.strip()}
        ALIASES.setdefault(norm(row["artist_name"]), set()).update(n for n in names if n)

def same_artist(ours, found):
    """True when the found credit names our artist (or a catalogue alias): exact, or as one of the credited names."""
    names = ALIASES.get(norm(ours), set()) | {norm(ours)}
    names.discard("")
    if not names or not found:
        return False
    if norm(found) in names:
        return True
    parts = re.split(r"\s*(?:,|&|\bfeat\.?|\bft\.?|\bx\b|\bet\b|\band\b)\s*", found, flags=re.I)
    return any(norm(part) in names for part in parts if part)

index, rejected, by_url = [], [], {}
for sid, c in sorted(covers.items()):
    if not c or c.get("match") not in ("song", "artist") or not c.get("art"):
        continue
    if not same_artist(c["artist"], c.get("found_artist")):
        rejected.append((sid, c["artist"], c.get("found_artist")))
        continue
    url = c["art"]
    if url not in by_url:
        name = hashlib.sha1(url.encode()).hexdigest()[:12]
        jpg, webp = raw / f"{name}.jpg", out / f"{name}.webp"
        if not webp.exists():
            req = urllib.request.Request(url, headers={"User-Agent": "catalogue-covers/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    jpg.write_bytes(r.read())
            except Exception as e:
                print("fail", sid, e); continue
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(jpg), "-vf", "scale=300:300", "-quality", "80", str(webp)], check=True)
            time.sleep(0.4)
        by_url[url] = webp.name
    index.append({
        "song_id": sid, "artist": c["artist"],
        "title": c["title"] if c["match"] == "song" else (c.get("found_track") or ""),
        "album": c.get("album") or "", "match": c["match"], "file": by_url[url],
    })

(out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
total = sum(f.stat().st_size for f in out.glob("*.webp"))
print(f"kept {len(index)} songs, {len(by_url)} images, {total/1e6:.1f} MB; rejected {len(rejected)} (artist mismatch)")
for r in rejected:
    print("  rejected", *r)
