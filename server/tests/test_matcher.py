"""B-T05: matcher worker — batches in, verdicts out (accepted and rejected), idempotent, feed events."""
import json
import logging

import numpy as np
import psycopg
import pytest

from server.db import EVENTS_CHANNEL, connect, jobs
from server.fp.index import DbIndex
from server.ingest import ingest_batch
from server.registry import upsert_meter
from server.tools.make_batches_from_wav import make_batches
from server.tools.make_test_vectors import OUT as TV_DIR
from server.workers import fingerprint, matcher
from server.workers.base import run_one
from server.tests.test_songs import melody, write_wav


@pytest.fixture(scope="module")
def catalogue(migrated_db, tmp_path_factory):
    """Two songs fingerprinted into the test db; returns {song_id: 48 kHz samples}."""
    d = tmp_path_factory.mktemp("cat")
    songs = {"S-000101": melody(21, 70), "S-000102": melody(22, 70)}
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE songs, owners, fp_hashes, flags RESTART IDENTITY CASCADE")
        keys = json.loads((TV_DIR / "tv_keys.json").read_text(encoding="utf-8"))
        with c.transaction():
            upsert_meter(c, keys)
        for sid, x in songs.items():
            p = write_wav(d / f"{sid}.wav", x)
            c.execute("INSERT INTO songs (song_id, title, artist_name, status, file_path) VALUES (%s, %s, 'T', 'uploaded', %s)",
                      (sid, f"Title {sid}", str(p)))
            assert fingerprint.process(c, f"{sid}:approved", DbIndex()) == "ready"
    return songs


@pytest.fixture(autouse=True)
def clean(migrated_db, catalogue):
    with connect(migrated_db, autocommit=True) as c:
        c.execute("TRUNCATE raw_batches, match_events, windows, jobs RESTART IDENTITY CASCADE")


def ingest_and_match(db, batches):
    idx = DbIndex()
    with connect(db, autocommit=True) as c:
        for b in batches:
            assert ingest_batch(c, b).code == 200
        rows = []
        while (job := jobs.claim(c, "match")) is not None:
            rows.append(matcher.process(c, int(job["ref"]), idx))
            jobs.done(c, job["id"])
    return rows


def test_clean_audio_at_least_90_percent(migrated_db, catalogue):
    rows = ingest_and_match(migrated_db, make_batches(catalogue["S-000102"], seq_start=1, n=6))
    ok = [r for r in rows if r["accepted"] and r["song_id"] == "S-000102"]
    assert len(ok) / len(rows) >= 0.9, [(r["song_id"], r["best_score"]) for r in rows]
    for i, r in enumerate(rows):                         # window i starts 10·i s into the song
        if r["accepted"]:
            assert abs(r["offset_s"] - 10 * i) < 0.1


def test_noisy_offset_audio(migrated_db, catalogue):
    """Off the frame grid (3.7 s) and noise at 10 dB SNR: still recognised, offsets advance with the clock."""
    rows = ingest_and_match(migrated_db, make_batches(catalogue["S-000101"], seq_start=1, offset_s=3.7, n=6, snr_db=10))
    acc = [r for r in rows if r["accepted"]]
    assert len(acc) >= 5 and all(r["song_id"] == "S-000101" for r in acc)
    for r in acc:
        k = rows.index(r)
        assert abs(r["offset_s"] - (3.7 + 10 * k)) < 0.1


def test_unknown_audio_rejected_but_recorded(migrated_db, catalogue):
    noise = np.random.default_rng(5).normal(0, 0.1, 48000 * 40).astype(np.float32)
    rows = ingest_and_match(migrated_db, make_batches(noise, seq_start=1, n=4) +
                            make_batches(melody(99, 30), seq_start=10, n=2))          # a song not in the catalogue
    assert len(rows) == 6 and not any(r["accepted"] for r in rows)
    with connect(migrated_db) as c:
        assert c.execute("SELECT count(*) AS n FROM match_events WHERE accepted = false").fetchone()["n"] == 6


def test_silent_window(migrated_db, catalogue):
    rows = ingest_and_match(migrated_db, make_batches(np.zeros(48000 * 10, np.float32), seq_start=1))
    assert len(rows) == 1 and rows[0]["accepted"] is False and rows[0]["song_id"] is None
    assert rows[0]["loudness_db"] == -100.0


def test_side_effects_and_idempotency(migrated_db, catalogue):
    rows = ingest_and_match(migrated_db, make_batches(catalogue["S-000101"], seq_start=1, n=3))
    with connect(migrated_db, autocommit=True) as c:
        assert c.execute("SELECT bool_and(processed) AS p FROM raw_batches").fetchone()["p"] is True
        play_jobs = c.execute("SELECT ref, status FROM jobs WHERE kind = 'play'").fetchall()
        assert play_jobs == [{"ref": "M-90", "status": "queued"}]            # one per meter, not one per batch
        again = matcher.process(c, rows[0]["raw_batch_id"], DbIndex())       # retried job
        assert again["id"] == rows[0]["id"]
        assert c.execute("SELECT count(*) AS n FROM match_events").fetchone()["n"] == 3


def test_match_event_on_feed(migrated_db, catalogue):
    with psycopg.connect(migrated_db, autocommit=True) as listener:
        listener.execute(f"LISTEN {EVENTS_CHANNEL}")
        ingest_and_match(migrated_db, make_batches(catalogue["S-000102"], seq_start=1, n=1, offset_s=20))
        events = [json.loads(n.payload) for n in listener.notifies(timeout=2, stop_after=3)]
    m = [e["data"] for e in events if e["event"] == "match"]
    assert len(m) == 1 and m[0]["accepted"] is True and m[0]["song_id"] == "S-000102"
    assert m[0]["title"] == "Title S-000102" and abs(m[0]["offset_s"] - 20) < 0.2


def test_job_loop_marks_missing_batch_as_error(migrated_db, catalogue):
    with connect(migrated_db, autocommit=True) as c:
        jobs.enqueue(c, "match", "999999")
        assert run_one(c, "match", matcher.handle, logging.getLogger("t")) is True
        assert c.execute("SELECT status FROM jobs WHERE ref = '999999'").fetchone()["status"] == "error"
