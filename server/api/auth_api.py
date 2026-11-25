"""Sign-in and the artist's own data (D-028).

POST /api/v1/auth/login   {"username","password"} -> sets the session cookie; {"user": {...,"role","home"}}
POST /api/v1/auth/logout
GET  /api/v1/auth/me      -> {"user": {...}} or 401
GET  /api/v1/me/songs     artist only: their songs (status, metadata) with plays and share per period — never other
                          artists, never bars
GET  /api/v1/public/recent-plays   anyone: the latest live plays as song, artist and CITY (never the bar)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fairplay_core.schema import format_utc
from server import auth
from server.api.admin import current_user
from server.db import connect
from server.stats.artists import artist_shares

router = APIRouter(prefix="/api/v1")
TEST_ARTIST = "Fair Play test artist"


class Login(BaseModel):
    username: str
    password: str


def _login(username: str, password: str, client: Optional[str]):
    from server import activity
    with connect(autocommit=True) as c:
        r = auth.login(c, username, password)
        if r:
            activity.record(c, "admin" if r["user"]["role"] == "sonacam" else "catalogue",
                            f"{r['user']['name']} signed in ({'SONACAM' if r['user']['role'] == 'sonacam' else 'artist portal'})",
                            actor=r["user"]["username"])
        else:
            activity.record(c, "admin", f"Failed sign-in as “{(username or '')[:60]}”", "warn", actor=client or "unknown")
        return r


@router.post("/auth/login")
async def login(body: Login, request: Request):
    r = await run_in_threadpool(_login, body.username, body.password, request.client.host if request.client else None)
    if r is None:
        return JSONResponse({"error": "wrong_login", "detail": "Wrong name or password."}, status_code=401)
    resp = JSONResponse({"user": r["user"]})
    resp.set_cookie(auth.COOKIE, r["token"], max_age=auth.SESSION_HOURS * 3600, httponly=True, samesite="lax",
                    secure=request.url.scheme == "https", path="/")
    return resp


def _logout(token: Optional[str]) -> None:
    with connect(autocommit=True) as c:
        auth.logout(c, token)


@router.post("/auth/logout")
async def logout(request: Request):
    await run_in_threadpool(_logout, request.cookies.get(auth.COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@router.get("/auth/me")
async def me(request: Request):
    u = await run_in_threadpool(current_user, request)
    if u is None:
        return JSONResponse({"error": "not_signed_in"}, status_code=401)
    return {"user": u}


def require_artist(request: Request) -> dict:
    u = current_user(request)
    if not u or u["role"] != "artist":
        raise HTTPException(403, detail="artists only: sign in with your artist name")
    return u


def _my_songs(artist_name: str) -> dict:
    with connect() as c:
        songs = c.execute("""SELECT song_id, title, artist_name, isrc, iswc, duration_s, status, n_hashes, uploaded_at,
                                    duplicate_of FROM songs WHERE artist_name = %s AND source = 'upload'
                             ORDER BY uploaded_at DESC, song_id DESC""", (artist_name,)).fetchall()
        owners = {}
        for o in c.execute("SELECT song_id, owner_name, role, share_pct FROM owners WHERE song_id = ANY(%s) ORDER BY song_id",
                           ([s["song_id"] for s in songs],)):
            owners.setdefault(o["song_id"], []).append({"name": o["owner_name"], "role": o["role"],
                                                        "share_pct": float(o["share_pct"])})
        periods = {}
        for period in ("live", "mock_month"):
            s = artist_shares(c, period, "standardised")
            row = next((r for r in s["rows"] if r["artist_name"] == artist_name), None)
            periods[period] = {"frozen": s["frozen"], "share": row["share"] if row else 0.0,
                               "all_counted": round(sum(r["counted_plays"] for r in s["rows"]), 2),
                               "counted_plays": row["counted_plays"] if row else 0, "raw_plays": row["raw_plays"] if row else 0,
                               "songs": {x["song_id"]: x for x in (row["songs"] if row else [])}}
    out = []
    for s in songs:
        per = {p: {k: v for k, v in (periods[p]["songs"].get(s["song_id"]) or {"share": 0.0, "counted_plays": 0, "raw_plays": 0}).items()
                   if k in ("share", "counted_plays", "raw_plays")} for p in periods}
        out.append({**s, "uploaded_at": format_utc(s["uploaded_at"]), "n_hashes": s["n_hashes"] or 0,
                    "owners": owners.get(s["song_id"], []), "periods": per})
    return {"artist_name": artist_name, "songs": out,
            "totals": {p: {k: periods[p][k] for k in ("share", "counted_plays", "raw_plays", "all_counted", "frozen")}
                       for p in periods}}


@router.get("/me/songs")
async def my_songs(user: dict = Depends(require_artist)):
    return await run_in_threadpool(_my_songs, user["artist_name"])


def _my_plays(artist_name: str, period: str, limit: int) -> dict:
    """When the artist's songs were played (Cameroon days) and the latest plays: song, time, how much it counted.
    Never the bar, the city or the meter (D-030)."""
    from server.api.read import query_plays
    from server.stats.periods import ACTIVE, period_sql
    where, args = period_sql(period)
    with connect() as c:
        recent = query_plays(c, period, "standardised", artist=artist_name, limit=limit)
        days = c.execute(f"""SELECT to_char((p.started_at AT TIME ZONE 'Africa/Douala')::date, 'YYYY-MM-DD') AS day,
                                    count(*) AS plays
                             FROM plays p JOIN songs s USING (song_id)
                             WHERE {ACTIVE} AND {where} AND s.artist_name = %s
                             GROUP BY 1 ORDER BY 1""", (*args, artist_name)).fetchall()
    return {"period": period,
            "days": [{"date": d["day"], "plays": d["plays"]} for d in days],
            "recent": [{"song_id": p["song_id"], "title": p["title"], "started_at": p["started_at"],
                        "duration_s": p.get("duration_s"), "weight": p.get("weight"),
                        "counted_less": p.get("weight") is not None and p["weight"] < 1} for p in recent]}


@router.get("/me/plays")
async def my_plays(period: str = Query("mock_month", pattern="^(live|mock_month)$"), limit: int = Query(30, ge=1, le=200),
                   user: dict = Depends(require_artist)):
    return await run_in_threadpool(_my_plays, user["artist_name"], period, limit)


def _recent(limit: int) -> list[dict]:
    with connect() as c:
        rows = c.execute("""SELECT s.title, s.artist_name, v.city, p.started_at FROM plays p
                            JOIN songs s USING (song_id) LEFT JOIN venues v ON v.venue_id = p.venue_id
                            WHERE p.chain = 'live' AND s.artist_name <> %s
                              AND NOT EXISTS (SELECT 1 FROM play_corrections x WHERE x.play_id = p.play_id
                                              AND x.reason = 'not_confirmed_on_recompute')
                            ORDER BY p.started_at DESC LIMIT %s""", (TEST_ARTIST, limit)).fetchall()
    return [{**r, "started_at": format_utc(r["started_at"])} for r in rows]


@router.get("/public/recent-plays")
async def recent_plays(limit: int = Query(5, ge=1, le=20)):
    return await run_in_threadpool(_recent, limit)
