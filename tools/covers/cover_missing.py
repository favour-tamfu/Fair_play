"""List catalogue songs with no usable cover yet, plus artist-only matches worth improving."""
import json, sys
from pathlib import Path

covers = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
index = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
have = {r["song_id"]: r for r in index}
missing = []
for sid, c in sorted(covers.items()):
    if sid in have and have[sid]["match"] == "song":
        continue
    reason = "no_match" if (not c or c.get("match") == "none") else ("artist_only" if sid in have else "download_failed_or_rejected")
    missing.append({"song_id": sid, "artist": c.get("artist"), "title": c.get("title"), "reason": reason,
                    "current_found": c.get("found_artist") and f'{c.get("found_artist")} - {c.get("found_track")}'})
out = Path(sys.argv[3])
out.write_text(json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8")
from collections import Counter
print(len(missing), Counter(m["reason"] for m in missing))
