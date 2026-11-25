"""Catalogue endpoints (contract §5): upload, list, detail, approve a suspected duplicate.

POST /api/v1/songs (multipart): file, title, artist_name, isrc?, iswc?, duration_s?, owners (JSON), consent="true"
  → 201 {"song_id","status":"uploaded"} ; 400 {"error","detail"} on any validation error (nothing stored).
The file goes to media/songs/<song_id><ext>; a "fingerprint" job is queued for the cataloguer worker.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from fairplay_core.schema import format_utc
from server import config
from server.api.admin import require_admin, require_uploader
from server.db import connect, jobs

router = APIRouter(prefix="/api/v1")
ROLES = {"singer", "composer", "producer", "publisher"}
MOMO_RE = re.compile(r"^\+?[0-9]{8,15}$")
SONG_FIELDS = "song_id, title, artist_name, isrc, iswc, duration_s, status, n_hashes, uploaded_at, duplicate_of"


class BadUpload(Exception):
    def __init__(self, detail: str):
        self.detail = detail


def parse_owners(raw: str) -> list[dict[str, Any]]:
    try:
        owners = json.loads(raw)
    except json.JSONDecodeError:
        raise BadUpload("owners must be a JSON list")
    if not isinstance(owners, list) or not owners:
        raise BadUpload("owners must be a non-empty JSON list")
    out = []
    for i, o in enumerate(owners):
        if not isinstance(o, dict):
            raise BadUpload(f"owners[{i}] must be an object")
        name = str(o.get("name", "")).strip()
        role = o.get("role")
        share = o.get("share_pct")
        momo = str(o.get("momo", "")).replace(" ", "")
        if not name:
            raise BadUpload(f"owners[{i}].name is required")
        if role not in ROLES:
            raise BadUpload(f"owners[{i}].role must be one of {sorted(ROLES)}")
        if isinstance(share, bool) or not isinstance(share, (int, float)) or not 0 < share <= 100:
            raise BadUpload(f"owners[{i}].share_pct must be a number in (0, 100]")
        if momo and not MOMO_RE.match(momo):   # optional (D-028): SONACAM keeps payment details on its own site
            raise BadUpload(f"owners[{i}].momo must be a phone number like +2376XXXXXXXX")
        out.append({"name": name, "role": role, "share_pct": float(share), "momo": momo or None})
    total = sum(o["share_pct"] for o in out)
    if abs(total - 100) > 0.01:
        raise BadUpload(f"owner shares must sum to 100 (got {total:g})")
    return out


def stored_path(p: Path) -> str:
    """Relative to the repo/app root when possible (same value inside the container and on the host)."""
    try:
        return p.resolve().relative_to(config.ROOT).as_posix()
    except ValueError:
        return str(p.resolve())


def resolve_path(s: str) -> Path:
    p = Path(s)
    return p if p.is_absolute() else config.ROOT / p


def _row_out(r: dict[str, Any]) -> dict[str, Any]:
    return {**r, "uploaded_at": format_utc(r["uploaded_at"]), "n_hashes": r["n_hashes"] or 0}


def _bad(detail: str) -> JSONResponse:
    return JSONResponse({"error": "invalid_upload", "detail": detail}, status_code=400)


def _save_upload(file: UploadFile, dest: Path) -> int:
    """Stream to disk; abort above the size limit. Returns bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            n += len(chunk)
            if n > config.UPLOAD_MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise BadUpload(f"file larger than {config.UPLOAD_MAX_BYTES // (1024 * 1024)} MB")
            out.write(chunk)
    if n == 0:
        dest.unlink(missing_ok=True)
        raise BadUpload("file is empty")
    return n


def _create(file: UploadFile, title: str, artist_name: str, isrc: Optional[str], iswc: Optional[str],
            duration_s: Optional[float], owners: list[dict[str, Any]]) -> str:
    ext = Path(file.filename or "").suffix.lower()
    with connect(autocommit=True) as conn:
        song_id = f"S-{conn.execute('SELECT nextval(%s) AS n', ('song_upload_seq',)).fetchone()['n']:06d}"
        dest = config.SONGS_DIR / f"{song_id}{ext}"
        _save_upload(file, dest)
        try:
            with conn.transaction():
                conn.execute("""INSERT INTO songs (song_id, title, artist_name, isrc, iswc, duration_s, status, file_path, source)
                                VALUES (%s, %s, %s, %s, %s, %s, 'uploaded', %s, 'upload')""",
                             (song_id, title, artist_name, isrc, iswc, duration_s, stored_path(dest)))
                for o in owners:
                    conn.execute("INSERT INTO owners (song_id, owner_name, role, share_pct, momo) VALUES (%s,%s,%s,%s,%s)",
                                 (song_id, o["name"], o["role"], o["share_pct"], o["momo"]))
                jobs.enqueue(conn, "fingerprint", song_id)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
    return song_id


@router.post("/songs", status_code=201)
async def upload_song(file: UploadFile = File(...), title: str = Form(...), artist_name: str = Form(...),
                      isrc: Optional[str] = Form(None), iswc: Optional[str] = Form(None),
                      duration_s: Optional[float] = Form(None), owners: str = Form(...),
                      consent: str = Form(...), who: dict = Depends(require_uploader)):
    try:
        if who.get("role") == "artist":               # D-028: an artist uploads under their own name only
            artist_name = who["artist_name"]
        if consent.strip().lower() != "true":
            raise BadUpload('consent must be "true" (rights holder agreed to royalty monitoring)')
        if Path(file.filename or "").suffix.lower() not in config.UPLOAD_EXTENSIONS:
            raise BadUpload(f"file type must be one of {sorted(config.UPLOAD_EXTENSIONS)}")
        title, artist_name = title.strip(), artist_name.strip()
        if not title or not artist_name:
            raise BadUpload("title and artist_name are required")
        if len(title) > 200 or len(artist_name) > 200:
            raise BadUpload("title / artist_name too long (max 200)")
        for name, v in (("isrc", isrc), ("iswc", iswc)):
            if v and len(v) > 20:
                raise BadUpload(f"{name} too long (max 20)")
        owner_list = parse_owners(owners)
        song_id = await run_in_threadpool(_create, file, title, artist_name, (isrc or None), (iswc or None),
                                          duration_s, owner_list)
    except BadUpload as e:
        return _bad(e.detail)
    return {"song_id": song_id, "status": "uploaded"}


def _list(status: Optional[str], q: Optional[str], source: str) -> list[dict[str, Any]]:
    sql, args = f"SELECT {SONG_FIELDS} FROM songs WHERE true", []
    if source != "all":
        sql += " AND source = %s"
        args.append(source)
    if status:
        sql += " AND status = %s"
        args.append(status)
    if q:
        sql += " AND (title ILIKE %s OR artist_name ILIKE %s OR song_id ILIKE %s)"
        args += [f"%{q}%"] * 3
    with connect() as conn:
        return [_row_out(r) for r in conn.execute(sql + " ORDER BY uploaded_at DESC, song_id DESC", args)]


@router.get("/songs")
async def list_songs(status: Optional[str] = None, q: Optional[str] = None,
                     source: str = Query("upload", pattern="^(upload|mock|all)$")):
    """Uploaded songs by default; ?source=mock|all to include the mock-month catalogue."""
    return await run_in_threadpool(_list, status, q, source)


def _detail(song_id: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        r = conn.execute(f"SELECT {SONG_FIELDS} FROM songs WHERE song_id = %s", (song_id,)).fetchone()
        if r is None:
            return None
        owners = conn.execute("SELECT owner_name AS name, role, share_pct, momo FROM owners WHERE song_id = %s ORDER BY id",
                              (song_id,)).fetchall()
    return {**_row_out(r), "owners": owners}


@router.get("/songs/{song_id}")
async def get_song(song_id: str):
    d = await run_in_threadpool(_detail, song_id)
    if d is None:
        raise HTTPException(404, detail="unknown song")
    return d


def _approve(song_id: str) -> Optional[str]:
    with connect(autocommit=True) as conn, conn.transaction():
        r = conn.execute("SELECT status FROM songs WHERE song_id = %s FOR UPDATE", (song_id,)).fetchone()
        if r is None:
            return None
        if r["status"] != "duplicate_suspected":
            return r["status"]
        conn.execute("UPDATE songs SET status = 'uploaded' WHERE song_id = %s", (song_id,))
        jobs.enqueue(conn, "fingerprint", f"{song_id}:approved")   # worker skips the duplicate check
    return "approved"


@router.post("/songs/{song_id}/approve", dependencies=[Depends(require_admin)])
async def approve_song(song_id: str):
    """Admin: a suspected duplicate is genuine (e.g. a remaster) → index it anyway."""
    res = await run_in_threadpool(_approve, song_id)
    if res is None:
        raise HTTPException(404, detail="unknown song")
    if res != "approved":
        return JSONResponse({"error": "not_duplicate_suspected", "detail": f"song status is {res}"}, status_code=409)
    return {"ok": True, "song_id": song_id, "status": "uploaded"}
