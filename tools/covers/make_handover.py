"""Build one handover zip for B: code bundle, v3 song package (audio), album art per song, docs, README."""
import csv, io, json, sys, zipfile
from pathlib import Path

repo, downloads = Path(sys.argv[1]), Path(sys.argv[2])
out = downloads / "Fair_Play_handover_for_B.zip"
covers_dir = repo / "web" / "assets" / "covers"
index = json.loads((covers_dir / "index.json").read_text(encoding="utf-8"))
catalogue = {r["catalogue_id"]: r for r in csv.DictReader(open(repo / "tools" / "mockgen" / "real_songs.csv", encoding="utf-8"))}

README = """# Fair Play — handover for Person B / Laptop B

Made on Laptop A, {date}. Branch a/work at commit {commit}.

## What is in this package
| Folder | What |
|---|---|
| code/Fair_Play_a-work.bundle | the whole a/work branch (web pages, dashboard, admin, covers in web/assets/covers, test data with real song names, handoffs) |
| songs/Fair_Play_song_package_v3.zip | the 183 verified Cameroonian songs (audio + catalogue.csv + not_included.csv + duplicates.csv) |
| covers/ | album art per song, named by catalogue id (FP-001.webp …), with covers.csv saying which album each comes from |
| meter/FairPlayMeter_windows.zip | the listener as FairPlayMeter.exe for a bar's Windows laptop (no Python needed); see its README |
| docs/ | latest handoff, STATUS_A, REQUESTS (read R-017 to R-020), SONACAM research report |

## Steps on Laptop B (PowerShell, in the Fair_play repo)
1. Get the code:
   git fetch <path>\\code\\Fair_Play_a-work.bundle a/work:refs/remotes/laptopA/a-work
   git merge laptopA/a-work
2. Re-import the mock month (its numbers changed) and, if you want, regenerate artist_shares.json (R-019).
3. Restart the server. Pages: / (public landing), /artist.html (Artists),
   /sonacam-x7k2q9.html (SONACAM dashboard), /sonacam-x7k2q9-admin.html (admin).
4. Load the songs: unzip songs/Fair_Play_song_package_v3.zip and upload the 183 songs from catalogue.csv
   (B currently holds only the 60 v1 songs, S-000013..S-000072).
5. Covers are already in the code (web/assets/covers, matched by artist and title). covers/ here is the same art
   keyed by catalogue id, for loading into the song records if useful.

## Notes
- Covers: 170 of 183 songs have one (163 the exact song, 7 another release by the same artist); 13 have none.
  Covers belong to their artists and labels and are shown only next to that artist's own songs.
- Test data: real titles and artists; bars, plays and amounts are simulated. The loop/promo scenarios use fictional
  "test track" songs so no real artist is shown cheating.
- Not tested against Laptop B's live server yet. Tests on A: scripts\\test_a.ps1 -> 88 passed; fixture checks 19 passed.
"""

with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
    import subprocess, datetime
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "a/work"], capture_output=True, text=True).stdout.strip()
    z.writestr("README_HANDOVER.md", README.format(date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), commit=commit))
    z.write(downloads / "Fair_Play_a-work.bundle", "code/Fair_Play_a-work.bundle", compress_type=zipfile.ZIP_STORED)
    z.write(downloads / "Fair_Play_song_package_v3.zip", "songs/Fair_Play_song_package_v3.zip", compress_type=zipfile.ZIP_STORED)
    if (downloads / "FairPlayMeter_windows.zip").exists():
        z.write(downloads / "FairPlayMeter_windows.zip", "meter/FairPlayMeter_windows.zip", compress_type=zipfile.ZIP_STORED)
    rows = io.StringIO(); w = csv.writer(rows)
    w.writerow(["song_id", "title", "artist_name", "cover_file", "match", "album", "source_image"])
    for c in sorted(index, key=lambda r: r["song_id"]):
        sid = c["song_id"]
        cat = catalogue.get(sid, {})
        name = f"{sid}.webp"
        z.write(covers_dir / c["file"], f"covers/{name}", compress_type=zipfile.ZIP_STORED)
        w.writerow([sid, cat.get("title", ""), cat.get("artist_name", c["artist"]), name, c["match"], c.get("album", ""), c["file"]])
    missing = [sid for sid in catalogue if sid not in {c["song_id"] for c in index}]
    for sid in missing:
        w.writerow([sid, catalogue[sid]["title"], catalogue[sid]["artist_name"], "", "none", "", ""])
    z.writestr("covers/covers.csv", rows.getvalue())
    docs = sorted((repo / "handoffs" / "A").glob("*.md"))[-1:] + [repo / "STATUS_A.md", repo / "REQUESTS.md",
            repo / "reports" / "SONACAM royalties and Fair Play fit.md"]
    for d in docs:
        z.write(d, f"docs/{d.name}")
print(out, f"{out.stat().st_size / 1e6:.1f} MB", f"covers {len(index)}, without cover {len(missing)}")
