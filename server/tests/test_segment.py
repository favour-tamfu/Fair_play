"""B-T06: the play segmenter (brief §6) as a pure function — every rule, including the repeated-section strays."""
from datetime import datetime, timedelta, timezone

from server.plays.segment import Event, segment

T0 = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)   # 21:00 in Buea


def ev(windows, song="S-000001", start_id=1, loud=-20.0):
    """windows: list of (seconds after T0, song offset) — None offset = rejected window."""
    out = []
    for i, (t, off) in enumerate(windows):
        acc = off is not None
        out.append(Event(start_id + i, T0 + timedelta(seconds=t), acc, song if acc else None, off or 0.0, loud))
    return out


def plays(events, length=240.0):
    return [c for c in segment(events, lambda s: length) if c.confirmed]


def test_plan_1_four_consecutive_windows_one_play():
    p = plays(ev([(0, 20), (10, 30), (20, 40), (30, 50)]))
    assert len(p) == 1 and p[0].n_windows == 4
    assert p[0].started_at == T0 - timedelta(seconds=20)      # heard 20 s into the song at T0
    assert p[0].ended_at == T0 + timedelta(seconds=40)


def test_plan_2_offset_jumps_back_two_plays():
    p = plays(ev([(0, 180), (10, 190), (20, 200), (30, 15), (40, 25), (50, 35)]))
    assert [(c.first_offset_s, c.n_windows) for c in p] == [(180, 3), (15, 3)]


def test_plan_3_chorus_repeat_with_clock_is_same_play():
    p = plays(ev([(0, 60), (80, 140)]))                       # offset +80 while the clock moved +80
    assert len(p) == 1 and p[0].n_windows == 2


def test_plan_4_single_stray_window_no_play():
    assert plays(ev([(0, 42)])) == []


def test_lone_offtrack_forward_window_is_ignored():
    """All Falls Down case: one window matched another copy of a looped section (+52.7 s)."""
    p = plays(ev([(0, 0), (10, 62.7), (20, 20), (30, 30), (40, 40)]))
    assert len(p) == 1 and p[0].n_windows == 4 and p[0].first_offset_s == 0


def test_lone_offtrack_backward_window_does_not_split_the_play():
    """Literal brief would start a new play on a −52.7 s jump; one stray must not split a play (D-007)."""
    p = plays(ev([(0, 60), (10, 70), (20, 27.3), (30, 90), (40, 100)]))
    assert len(p) == 1 and p[0].n_windows == 4


def test_two_agreeing_forward_windows_are_a_skip_in_the_same_play():
    p = plays(ev([(0, 10), (10, 20), (20, 100), (30, 110), (40, 120)]))
    assert len(p) == 1 and p[0].n_windows == 5 and p[0].last_offset_s == 120


def test_different_song_closes_the_play():
    e = ev([(0, 0), (10, 10), (20, 20)], song="S-000001") + ev([(30, 0), (40, 10), (50, 20)], song="S-000002", start_id=10)
    assert [c.song_id for c in plays(e)] == ["S-000001", "S-000002"]


def test_same_song_replayed_after_its_end_is_a_new_play():
    e = ev([(0, 10), (10, 20), (20, 30), (30, 40), (200, 10), (210, 20), (220, 30)])
    assert len(plays(e, length=60.0)) == 2                    # gap 170 s > (60 − 40) + 60


def test_confirmation_needs_coverage():
    assert plays(ev([(0, 0), (10, 10)]), length=300) == []                  # covered 20 s < min(30, 90)
    assert len(plays(ev([(0, 0), (10, 10), (20, 20)]), length=300)) == 1    # covered 30 s
    assert len(plays(ev([(0, 0), (10, 10)]), length=60)) == 1               # short song: min(30, 18) = 18 s


def test_rejected_windows_inside_a_play_do_not_break_it():
    p = plays(ev([(0, 0), (10, None), (20, 20), (30, None), (40, 40)]))
    assert len(p) == 1 and p[0].n_windows == 3


def test_started_at_never_more_than_one_song_length_back():
    p = plays(ev([(0, 500), (10, 510), (20, 520)]), length=240)
    assert p[0].started_at == T0 - timedelta(seconds=240)


def test_events_out_of_arrival_order_give_the_same_plays_once_sorted():
    e = ev([(0, 20), (10, 30), (20, 40), (30, 50)])
    shuffled = [e[2], e[0], e[3], e[1]]
    assert [(c.first_offset_s, c.n_windows) for c in plays(sorted(shuffled, key=lambda x: x.window_start))] == [(20, 4)]
