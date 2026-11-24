"""B-T04: song upload API, fingerprint worker, duplicate check, approve, DbIndex."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.io import wavfile

from fairplay_core.constants import WINDOW_SAMPLES
from fairplay_core.landmarks import make_hashes, match_window
from fairplay_core.peaks import extract_peaks, resample_to_8k
from server import config
from server.db import connect, jobs
from server.fp.index import DbIndex
from server.workers import fingerprint
from server.workers.base import run_one

OWNERS = [{"name": "Ada Singer", "role": "singer", "share_pct": 50, "momo": "+237699000001"},
          {"name": "Ben Composer", "role": "composer", "share_pct": 30, "momo": "+237699000002"},
          {"name": "Cy Producer", "role": "producer", "share_pct": 20, "momo": "+237699000003"}]


def melody(seed: int, seconds: float = 40.0, sr: int = 48000) -> np.ndarray:
    """A deterministic 'song': random notes (with harmonics) every 0.25 s, plus a little noise."""
    rng = np.random.default_rng(seed)
    n_note = int(0.25 * sr)
    t = np.arange(n_note) / sr
    env = np.minimum(1, np.minimum(t, t[::-1]) * 40)
    notes = []
    for _ in range(int(seconds / 0.25)):
        f = 110 * 2 ** (rng.integers(0, 36) / 12)
        notes.append(env * sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 2, 3)))
    x = np.concatenate(notes) * 0.3 + rng.normal(0, 0.003, n_note * len(notes))
    return x.astype(np.float32)


def write_wav(path, x, sr=48000):
    wavfile.write(path, sr, (np.clip(x, -1, 1) * 32767).astype(np.int16))
    return path


@pytest.fixture(scope="module")
def client(migrated_db, tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DATABASE_URL", migrated_db)
    mp.setattr(config, "SONGS_DIR", tmp_path_factory.mktemp("media") / "songs")
    from server.api.main import app
    with TestClient(app) as c:
        yield c
    mp.undo()


@pytest.fixture(autouse=True)
def clean(migrated_db):
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE songs, owners, fp_hashes, flags, jobs RESTART IDENTITY CASCADE")
        c.execute("ALTER SEQUENCE song_upload_seq RESTART WITH 1")


@pytest.fixture(scope="module")
def wavs(tmp_path_factory):
    d = tmp_path_factory.mktemp("wavs")
    return {k: write_wav(d / f"{k}.wav", melody(seed)) for k, seed in (("a", 1), ("b", 2), ("c", 3))}


def upload(client, path, title="Song", owners=OWNERS, consent="true", name=None, **fields):
    with open(path, "rb") as f:
        return client.post("/api/v1/songs", files={"file": (name or path.name, f, "audio/wav")},
                           data={"title": title, "artist_name": "Test Artist", "owners": json.dumps(owners),
                                 "consent": consent, **fields})


def work(db, index=None):
    """Run every queued fingerprint job (like the worker would)."""
    index = index or DbIndex()
    out = []
    with connect(db, autocommit=True) as c:
        while (job := jobs.claim(c, "fingerprint")) is not None:
            out.append(fingerprint.process(c, job["ref"], index))
            jobs.done(c, job["id"])
    return out


def song(db, song_id):
    with connect(db) as c:
        return c.execute("SELECT * FROM songs WHERE song_id = %s", (song_id,)).fetchone()


# ---------------------------------------------------------------- upload validation

def test_upload_ok_stores_file_owners_and_job(client, migrated_db, wavs):
    r = upload(client, wavs["a"], title="First", isrc="CM-ABC-26-00001")
    assert (r.status_code, r.json()) == (201, {"song_id": "S-000001", "status": "uploaded"})
    s = song(migrated_db, "S-000001")
    assert s["status"] == "uploaded" and s["isrc"] == "CM-ABC-26-00001" and s["source"] == "upload"
    assert (config.SONGS_DIR / "S-000001.wav").stat().st_size == wavs["a"].stat().st_size
    with connect(migrated_db) as c:
        assert len(c.execute("SELECT * FROM owners WHERE song_id='S-000001'").fetchall()) == 3
        assert c.execute("SELECT kind, ref FROM jobs").fetchall() == [{"kind": "fingerprint", "ref": "S-000001"}]
    assert upload(client, wavs["b"]).json()["song_id"] == "S-000002"          # sequential ids


@pytest.mark.parametrize("change, why", [
    ({"consent": "false"}, "consent"),
    ({"owners": [{**OWNERS[0], "share_pct": 60}, OWNERS[1], OWNERS[2]]}, "sum 110"),
    ({"owners": [{**OWNERS[0], "role": "dj"}]}, "role"),
    ({"owners": [{**OWNERS[0], "momo": "call me"}]}, "momo"),
    ({"owners": []}, "no owners"),
    ({"name": "song.exe"}, "extension"),
    ({"title": "  "}, "empty title"),
])
def test_upload_rejected_400(client, migrated_db, wavs, change, why):
    r = upload(client, wavs["a"], **change)
    assert r.status_code == 400 and r.json()["error"] == "invalid_upload", why
    with connect(migrated_db) as c:
        assert c.execute("SELECT count(*) AS n FROM songs").fetchone()["n"] == 0


def test_owners_not_json_400(client, wavs):
    with open(wavs["a"], "rb") as f:
        r = client.post("/api/v1/songs", files={"file": ("a.wav", f)},
                        data={"title": "x", "artist_name": "y", "owners": "not json", "consent": "true"})
    assert r.status_code == 400


def test_too_large_400(client, wavs, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_MAX_BYTES", 1000)
    assert upload(client, wavs["a"]).status_code == 400
    assert not (config.SONGS_DIR / "S-000001.wav").exists()          # partial file removed


# ---------------------------------------------------------------- fingerprint worker + duplicates

def test_fingerprint_makes_song_ready_and_matchable(client, migrated_db, wavs):
    upload(client, wavs["a"])
    assert work(migrated_db) == ["ready"]
    s = song(migrated_db, "S-000001")
    assert s["status"] == "ready" and s["n_hashes"] > 500 and abs(s["duration_s"] - 40.0) < 0.1
    idx = DbIndex()
    with connect(migrated_db) as c:
        assert idx.sync(c) == (["S-000001"], [])
        assert c.execute("SELECT count(*) AS n FROM fp_hashes").fetchone()["n"] == s["n_hashes"]
    # a 10 s window cut at an arbitrary point (like a meter would hear it) matches the indexed song
    x8 = resample_to_8k(melody(1))[int(13.37 * 8000):][:WINDOW_SAMPLES]
    r = match_window(make_hashes(extract_peaks(x8)), idx)
    assert r.accepted and r.song_id == "S-000001" and abs(r.offset_s - 13.37) < 0.05


def test_duplicate_detected_then_approved(client, migrated_db, wavs):
    upload(client, wavs["a"], title="Original")
    upload(client, wavs["b"], title="Different song")
    assert work(migrated_db) == ["ready", "ready"]                 # b is not a duplicate of a
    upload(client, wavs["a"], title="Same file again")             # S-000003
    assert work(migrated_db) == ["duplicate_suspected"]
    s = song(migrated_db, "S-000003")
    assert s["status"] == "duplicate_suspected" and s["duplicate_of"] == "S-000001" and s["n_hashes"] == 0
    with connect(migrated_db) as c:
        f = c.execute("SELECT type, song_id, detail FROM flags").fetchall()
        assert f == [{"type": "duplicate_suspected", "song_id": "S-000003", "detail": "upload matches S-000001 in 3/3 slices"}]
        assert c.execute("SELECT count(*) AS n FROM fp_hashes WHERE song_id='S-000003'").fetchone()["n"] == 0
    detail = client.get("/api/v1/songs/S-000003").json()
    assert detail["duplicate_of"] == "S-000001" and len(detail["owners"]) == 3

    assert client.post("/api/v1/songs/S-000002/approve").status_code == 409    # not a suspected duplicate
    assert client.post("/api/v1/songs/S-000003/approve").json()["ok"] is True
    assert work(migrated_db) == ["ready"]
    s = song(migrated_db, "S-000003")
    assert s["status"] == "ready" and s["duplicate_of"] is None and s["n_hashes"] > 0


def test_duplicate_of_a_reencoded_quieter_copy(client, migrated_db, wavs, tmp_path):
    """Same recording re-exported at another sample rate and 6 dB quieter is still caught."""
    upload(client, wavs["c"])
    work(migrated_db)
    x = melody(3) * 0.5
    copy = write_wav(tmp_path / "copy44k.wav", resample_to_8k(x).repeat(1), sr=8000)   # 8 kHz export
    upload(client, copy)
    assert work(migrated_db) == ["duplicate_suspected"]


def test_broken_file_marked_failed(client, migrated_db, tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"RIFF....not really a wav")
    upload(client, bad)
    with connect(migrated_db, autocommit=True) as c:
        import logging
        assert run_one(c, "fingerprint", fingerprint.handle, logging.getLogger("t")) is True
        assert c.execute("SELECT status, error FROM jobs").fetchone()["status"] == "error"
    assert song(migrated_db, "S-000001")["status"] == "failed"


# ---------------------------------------------------------------- list / detail / index

def test_list_filter_and_detail(client, migrated_db, wavs):
    upload(client, wavs["a"], title="Makossa Night")
    upload(client, wavs["b"], title="Bikutsi Morning")
    work(migrated_db)
    rows = client.get("/api/v1/songs").json()
    assert [r["song_id"] for r in rows] == ["S-000002", "S-000001"]                 # newest first
    assert [r["title"] for r in client.get("/api/v1/songs", params={"q": "makossa"}).json()] == ["Makossa Night"]
    assert client.get("/api/v1/songs", params={"status": "failed"}).json() == []
    assert client.get("/api/v1/songs/S-000009").status_code == 404
    from jsonschema import Draft202012Validator
    for name, body in (("songs", rows), ("song", client.get("/api/v1/songs/S-000001").json())):
        schema = json.loads((config.SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert list(Draft202012Validator(schema).iter_errors(body)) == []


def test_dbindex_sync_adds_and_removes(client, migrated_db, wavs):
    upload(client, wavs["a"])
    upload(client, wavs["b"])
    work(migrated_db)
    idx = DbIndex()
    with connect(migrated_db, autocommit=True) as c:
        assert sorted(idx.sync(c)[0]) == ["S-000001", "S-000002"]
        assert idx.sync(c) == ([], [])                                  # nothing changed → nothing reloaded
        c.execute("UPDATE songs SET status = 'failed' WHERE song_id = 'S-000002'")
        assert idx.sync(c) == ([], ["S-000002"])
        assert set(idx.songs) == {"S-000001"}
        assert all(s == "S-000001" for entries in idx._d.values() for s, _ in entries)


def test_upload_limit_is_50_mb():
    """contract c-1.1 (proposed): 30 → 50 MB."""
    assert config.UPLOAD_MAX_BYTES == 50 * 1024 * 1024


def test_half_hop_index_strengthens_off_grid_windows(monkeypatch):
    """A window starting half a hop off the song's frame grid (the normal case for a live meter) scores much higher
    and lands on the right position when the catalogue also indexes the half-hop-shifted grid (D-006)."""
    from fairplay_core.landmarks import MemoryIndex
    x8 = resample_to_8k(melody(1))
    results = {}
    for shifts in ((0,), (0, 128)):
        monkeypatch.setattr(config, "FP_INDEX_SHIFTS", shifts)
        idx = MemoryIndex()
        idx.add("S-000001", fingerprint.song_hashes(x8))
        scores = []
        for k in (100, 300, 500, 700):                       # windows at frame k + 0.5 (128 samples off the grid)
            w = x8[k * 256 + 128:][:WINDOW_SAMPLES]
            r = match_window(make_hashes(extract_peaks(w)), idx)
            assert r.accepted and r.song_id == "S-000001" and abs(r.offset_frames - (k + 0.5)) <= 1
            scores.append(r.best_score)
        results[shifts] = min(scores)
    assert results[(0, 128)] >= 2 * results[(0,)], results
