"""B-T09: fair-play weights sr-1.0 — brief §7.1 test vectors exactly, reference-algorithm equivalence, §7.2 modifiers."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from server import config
from server.stats import modifiers
from server.stats.fairplay import compute_weights, event_order, streak_weights, to_ns

DAY = datetime(2026, 11, 24, tzinfo=timezone.utc)


def at(hhmm: str, day=DAY) -> datetime:
    """Local Cameroon time (UTC+1) -> UTC datetime."""
    h, m = map(int, hhmm.split(":"))
    return day + timedelta(hours=h - config.LOCAL_UTC_OFFSET_H, minutes=m)


def plays(rows, venue="V-1"):
    """rows: [(hh:mm, song)] or [(datetime, song)] -> plays frame."""
    out = []
    for i, (t, s) in enumerate(rows):
        out.append({"play_id": f"P-{venue}-{i:04d}", "venue_id": venue, "meter_id": f"M-{venue}", "song_id": s,
                    "started_at": at(t) if isinstance(t, str) else t})
    return pd.DataFrame(out)


def run(df, **kw):
    r = compute_weights(df, **kw)
    return list(r.weights["weight"]), [x[0] for x in r.weights["reasons"]], r


# ---------------------------------------------------------------- brief §7.1 test vectors (exact)

def test_T_SR_1_cooldown():
    df = plays([("21:00", "A"), ("21:04", "A"), ("21:08", "A"), ("21:12", "A"), ("21:16", "B"), ("21:20", "A"),
                ("21:24", "C"), ("21:28", "D"), ("22:00", "A"), ("23:15", "A")])
    w, why, _ = run(df)
    assert w == [1, 1, 0.5, 0.25, 1, 0, 1, 1, 0, 1]
    assert why == ["streak_1", "streak_2", "streak_3", "streak_4", "streak_1", "cooldown", "streak_1", "streak_1",
                   "cooldown", "streak_1"]
    a = df["song_id"] == "A"
    assert a.sum() == 7 and sum(np.array(w)[a]) == 3.75                     # "Total raw A = 7, counted A = 3.75"


def test_T_SR_2_normal_reset():
    w, why, _ = run(plays([("20:00", "A"), ("20:05", "A"), ("20:10", "B"), ("20:15", "C"), ("20:20", "D"), ("20:40", "A")]))
    assert w == [1, 1, 1, 1, 1, 1] and why[-1] == "streak_1"


def test_T_SR_3_no_reset_too_soon():
    w, why, _ = run(plays([("20:00", "A"), ("20:04", "A"), ("20:06", "B"), ("20:08", "C"), ("20:10", "D"), ("20:12", "A")]))
    assert w[-1] == 0.5 and why[-1] == "streak_3"


def test_cooldown_needs_three_others_even_after_two_hours():
    w, why, _ = run(plays([("20:00", "A"), ("20:01", "A"), ("20:02", "A"), ("20:03", "A"), ("23:00", "B"),
                           ("23:30", "A"), ("23:31", "C"), ("23:33", "A"), ("23:34", "D"), ("23:35", "A")]))
    assert why[5] == "cooldown" and why[7] == "cooldown"          # 1 other, then 2 others (A's own play not counted)
    assert why[9] == "streak_1" and w[9] == 1                      # B, C, D = 3 others and > 2 h -> cooldown over


def test_venues_are_independent_and_order_by_event_time():
    a = plays([("21:00", "A"), ("21:04", "A"), ("21:08", "A")], venue="V-1")
    b = plays([("21:01", "A"), ("21:05", "A")], venue="V-2")
    df = pd.concat([a, b], ignore_index=True)
    shuffled = df.sample(frac=1, random_state=3).reset_index(drop=True)
    r = compute_weights(shuffled).weights
    assert list(r["play_id"]) == list(shuffled["play_id"])                   # output rows follow input order
    got = dict(zip(r["play_id"], r["weight"]))
    assert [got[p] for p in a["play_id"]] == [1, 1, 0.5] and [got[p] for p in b["play_id"]] == [1, 1]


def reference(df):
    """Brief §7.1 reference algorithm, transcribed line by line (O(plays × songs))."""
    out = {}
    for _, vp in df.sort_values(["venue_id", "started_at", "play_id"]).groupby("venue_id"):
        state = {}
        for play in vp.itertuples():
            for s in state:
                if s != play.song_id:
                    state[s]["others_since"] += 1
            st = state.setdefault(play.song_id, {"streak": 0, "last_play": None, "cooldown_until": None, "others_since": 0})
            if st["cooldown_until"] is not None:
                if play.started_at >= st["cooldown_until"] and st["others_since"] >= 3:
                    st["cooldown_until"] = None
                    st["streak"] = 0
                else:
                    out[play.play_id] = (0, "cooldown")
                    st["last_play"] = play.started_at
                    continue
            if st["streak"] > 0 and st["others_since"] >= 3 and play.started_at - st["last_play"] >= timedelta(minutes=30):
                st["streak"] = 0
            st["streak"] += 1
            out[play.play_id] = ([1, 1, 0.5, 0.25][st["streak"] - 1], "streak_%d" % st["streak"])
            if st["streak"] == 4:
                st["cooldown_until"] = play.started_at + timedelta(hours=2)
                st["others_since"] = 0
            st["last_play"] = play.started_at
            st["others_since"] = 0
    return out


@pytest.mark.parametrize("seed", range(6))
def test_fast_streak_equals_reference_algorithm(seed):
    rng = np.random.default_rng(seed)
    n = 1500
    df = pd.DataFrame({
        "play_id": [f"P-{i:05d}" for i in range(n)],
        "venue_id": rng.choice(["V-1", "V-2", "V-3"], n),
        "song_id": rng.choice([f"S-{k}" for k in range(4 + seed * 3)], n, p=None),
        "started_at": [DAY + timedelta(minutes=int(m)) for m in np.sort(rng.integers(0, 3 * 24 * 60, n))],
    })
    ref = reference(df)
    sh = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    o = event_order(sh)
    w, why = streak_weights(sh["venue_id"].to_numpy()[o], sh["song_id"].to_numpy()[o], to_ns(sh["started_at"])[o])
    got = {p: (wi, r) for p, wi, r in zip(sh["play_id"].to_numpy()[o], w, why)}
    assert got == ref
    assert sum(1 for v in ref.values() if v[1] == "cooldown") > 0              # the scenario actually exercised cooldown


def test_deterministic_and_rule_version():
    df = plays([("21:00", "A"), ("21:04", "A"), ("21:04", "B"), ("21:08", "A")])
    assert compute_weights(df).weights.equals(compute_weights(df).weights)
    with pytest.raises(ValueError):
        compute_weights(df, rule_version="sr-9")
    assert compute_weights(df.iloc[:0]).weights.empty


# ---------------------------------------------------------------- loop flag

def test_loop_flag_back_to_back_one_song_length_apart():
    songs = pd.DataFrame({"song_id": ["A", "B"], "duration_s": [240.0, 200.0]})
    t0 = at("21:00")
    looping = plays([(t0 + timedelta(seconds=240 * k + (10 if k % 2 else -5)), "A") for k in range(5)])
    w, why, r = run(looping, songs=songs)
    assert all("loop" in rs for rs in r.weights["reasons"])
    assert w == [1, 1, 0.5, 0.25, 0]                                         # weights from 7.1, loop adds no change
    loops = [f for f in r.flags if f["type"] == "loop"]
    assert len(loops) == 1 and loops[0]["song_id"] == "A" and loops[0]["detail"].startswith("5 back-to-back")

    broken = plays([(t0, "A"), (t0 + timedelta(seconds=240), "A"), (t0 + timedelta(seconds=480), "B"),
                    (t0 + timedelta(seconds=680), "A"), (t0 + timedelta(seconds=920), "A")])
    assert not any(f["type"] == "loop" for f in compute_weights(broken, songs=songs).flags)        # B in between
    slow = plays([(t0 + timedelta(seconds=300 * k), "A") for k in range(5)])                       # 60 s gaps too long
    assert not any(f["type"] == "loop" for f in compute_weights(slow, songs=songs).flags)


# ---------------------------------------------------------------- audience factor

def spread_night(n, venue="V-1", start="20:00", every_min=6):
    """n plays of distinct songs (no streak effects) across the evening."""
    return plays([(at(start) + timedelta(minutes=every_min * i), f"S-{i}") for i in range(n)], venue=venue)


@pytest.fixture
def adjust(monkeypatch):
    """Brief §7.2 original behaviour: modifiers change the weights (off by default, D-009)."""
    monkeypatch.setattr(config, "MODIFIERS_ADJUST_WEIGHTS", True)


def test_low_audience_quiet_room_flag_only_by_default():
    assert config.MODIFIERS_ADJUST_WEIGHTS is False                              # D-009
    df = spread_night(10)
    df["loudness_db"] = [-20.0] * 9 + [-70.0]
    windows = pd.DataFrame({"meter_id": "M-V-1", "loudness_db": np.linspace(-60, -10, 120), "received": True})
    w, _, r = run(df, windows=windows)
    assert w == [1] * 10 and r.weights["reasons"].iloc[-1] == ["streak_1", "low_audience"]
    assert [(f["type"], f["detail"]) for f in r.flags] ==         [("low_audience", "1 plays for review (quiet room: 1, outside active hours: 0)")]


def test_low_audience_quiet_room_halves_when_enabled(adjust):
    df = spread_night(10)
    df["loudness_db"] = [-20.0] * 9 + [-70.0]
    windows = pd.DataFrame({"meter_id": "M-V-1", "loudness_db": np.linspace(-60, -10, 120), "received": True})
    w, _, r = run(df, windows=windows)
    assert w == [1] * 9 + [0.5] and r.weights["reasons"].iloc[-1] == ["streak_1", "low_audience"]
    assert [f["type"] for f in r.flags] == ["low_audience"]
    few = windows.iloc[: config.AUDIENCE_MIN_WINDOWS - 1]                        # D-008: too few windows -> no test
    assert run(df, windows=few)[2].flags == []


def test_low_audience_outside_active_hours(adjust):
    df = spread_night(60, every_min=1)                                            # 20:00-20:59 local
    odd = plays([("10:30", "X")]).assign(play_id="P-odd")
    w, _, r = run(pd.concat([df, odd], ignore_index=True))
    assert w[-1] == 0.5 and w[:-1] == [1] * 60
    assert "outside active hours: 1" in r.flags[0]["detail"]
    small = pd.concat([df.iloc[:20], odd], ignore_index=True)                    # D-008: < 50 plays -> no test
    assert run(small)[0] == [1] * 21 and run(small)[2].flags == []


# ---------------------------------------------------------------- concentration cap

def promo_world():
    rows = []
    for v in range(6):                                  # 6 venues, each with 6 one-off songs -> median weighted plays = 1
        rows += [(at("20:00") + timedelta(minutes=10 * i), f"S-{v}-{i}") for i in range(6)]
    df = pd.concat([plays(rows[6 * v: 6 * v + 6], venue=f"V-{v}") for v in range(6)], ignore_index=True)
    # promoted song P: 9 counted plays in V-0 alone (spread out with 3 others + 30 min between, so all weight 1)
    promo = []
    for k in range(9):
        t = at("18:00") + timedelta(days=k)
        promo += [(t, "P"), (t + timedelta(minutes=1), "Q1"), (t + timedelta(minutes=2), "Q2"), (t + timedelta(minutes=3), "Q3")]
    return pd.concat([df, plays(promo, venue="V-0").assign(play_id=lambda d: "Pp" + d["play_id"])], ignore_index=True)


def test_concentration_flag_only_by_default():
    df = promo_world()
    r = compute_weights(df)
    wp = r.weights[df["song_id"].to_numpy() == "P"]
    assert wp["weight"].sum() == 9 and all("concentration" in rs for rs in wp["reasons"])
    assert any(f["song_id"] == "P" and f["detail"].endswith("cap 5 per venue, 1 venue(s) above it (for review)")
               for f in r.flags if f["type"] == "concentration")


def test_concentration_cap_when_enabled(adjust):
    df = promo_world()
    r = compute_weights(df)
    wp = r.weights[df["song_id"].to_numpy() == "P"]
    cap = max(config.CONC_CAP_MIN, config.CONC_CAP_MULT * 1.0)                    # = 5
    assert wp["weight"].sum() == pytest.approx(cap)
    assert all("concentration" in rs for rs in wp["reasons"])
    conc = [f for f in r.flags if f["type"] == "concentration"]
    assert any(f["song_id"] == "P" and "cap 5 per venue, 1 venue(s) capped" in f["detail"] for f in conc)
    # Q1..Q3 (9 plays each, also only in V-0) are capped too; one-off songs are flagged but untouched (1 <= cap)
    assert r.weights[df["song_id"].str.startswith("S-").to_numpy()]["weight"].eq(1).all()


def test_concentration_skipped_with_few_venues_in_period(adjust):
    rows = []                                                                     # one venue (live demo)
    for k in range(12):
        t = at("18:00") + timedelta(days=k)
        rows += [(t, "P")] + [(t + timedelta(minutes=5 * j), f"O{j}") for j in (1, 2, 3)]
    w, _, r = run(plays(rows))
    w = [x for x, (_, s) in zip(w, rows) if s == "P"]
    assert sum(w) == 12 and not any(f["type"] == "concentration" for f in r.flags)


def test_cooldown_summary_flag():
    df = plays([("21:00", "A"), ("21:03", "A"), ("21:06", "A"), ("21:09", "A"), ("21:12", "A")])
    flags = compute_weights(df).flags
    assert flags == [{"type": "cooldown", "song_id": "A", "venue_id": "V-1", "meter_id": None,
                      "detail": "5 plays -> 2.75 counted, 1 in cooldown"}]


def test_song_lengths_default():
    p = pd.DataFrame({"song_id": ["A", "Z"]})
    assert list(modifiers.song_lengths(p, pd.DataFrame({"song_id": ["A"], "duration_s": [180.0]}))) == \
        [180.0, config.DEFAULT_SONG_LENGTH_S]
