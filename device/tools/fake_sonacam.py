"""Fake SONACAM server for device tests (A-T04). Implements contract 01 §4.

Run:  uvicorn device.tools.fake_sonacam:app --port 8001

Behaviour (contract §4):
  POST /v1/batches        200 stored | 200 duplicate | 401 bad_signature | 404 unknown_meter
                          409 seq_conflict | 422 invalid
  POST /v1/batches/bulk   {"batches":[...<=50]} -> {"results":[{seq,status,error?}]}
  POST /v1/heartbeat      signed like a batch -> {"ok":true,"server_time":"...Z"}
  GET  /health            {"ok":true,"server_time":"...Z"}

Test controls (not in the contract):
  POST /_chaos  {"fail_rate": 0.5, "latency_ms": 800, "down": true}   (fields optional)
  POST /_reset  clears stored batches and chaos settings
Keys come from contract/meters/*.pub.json (loaded at startup, or passed to create_app).
"""
import base64
import glob
import json
import os
import random
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from device.agent.batcher import verify_fields

METERS_DIR = os.path.join("contract", "meters")
BULK_MAX = 50
FP_VERSION = "fp-1.0"
REQUIRED = ("v", "fp_version", "meter_id", "venue_id", "seq", "window_start", "window_ms",
            "loudness_db", "cell_id", "fw", "n_peaks", "peaks_b64", "sig")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_keys(meters_dir: str = METERS_DIR) -> dict:
    keys = {}
    for path in glob.glob(os.path.join(meters_dir, "*.pub.json")):
        with open(path, encoding="utf-8") as fh:
            pub = json.load(fh)
        keys[pub["meter_id"]] = pub["public_key_b64"]
    return keys


class FakeSonacam:
    def __init__(self, keys: dict):
        self.keys = keys
        self.lock = threading.Lock()
        self.stored = {}          # (meter_id, seq) -> batch dict
        self.heartbeats = []
        self.chaos = {"fail_rate": 0.0, "latency_ms": 0, "down": False}

    def reset(self):
        with self.lock:
            self.stored.clear()
            self.heartbeats.clear()
            self.chaos = {"fail_rate": 0.0, "latency_ms": 0, "down": False}

    def check_batch(self, batch) -> tuple:
        """Return (status_code, body) for one batch, without chaos applied."""
        if not isinstance(batch, dict) or any(k not in batch for k in REQUIRED):
            return 422, {"error": "invalid", "detail": "missing fields"}
        if batch["v"] != 1 or batch["fp_version"] != FP_VERSION:
            return 422, {"error": "invalid", "detail": "unsupported version"}
        meter = batch["meter_id"]
        if meter not in self.keys:
            return 404, {"error": "unknown_meter"}
        if not verify_fields(self.keys[meter], batch):
            return 401, {"error": "bad_signature"}
        key = (meter, int(batch["seq"]))
        with self.lock:
            existing = self.stored.get(key)
            if existing is not None:
                if existing["sig"] == batch["sig"]:
                    return 200, {"ack": batch["seq"], "status": "duplicate"}
                return 409, {"error": "seq_conflict"}
            self.stored[key] = dict(batch)
        return 200, {"ack": batch["seq"], "status": "stored"}


def create_app(keys: dict = None) -> FastAPI:
    state = FakeSonacam(load_keys() if keys is None else keys)
    app = FastAPI(title="fake SONACAM (device tests)")
    app.state.sonacam = state

    def chaos_response():
        c = state.chaos
        if c["latency_ms"]:
            time.sleep(c["latency_ms"] / 1000.0)
        if c["down"]:
            return JSONResponse({"error": "down"}, status_code=503)
        if c["fail_rate"] and random.random() < c["fail_rate"]:
            return JSONResponse({"error": "server_error"}, status_code=500)
        return None

    @app.get("/health")
    def health():
        return {"ok": True, "server_time": _now()}

    @app.post("/v1/batches")
    async def post_batch(request: Request):
        failed = chaos_response()
        if failed is not None:
            return failed
        try:
            batch = await request.json()
        except ValueError:
            return JSONResponse({"error": "invalid", "detail": "bad json"}, status_code=422)
        code, body = state.check_batch(batch)
        return JSONResponse(body, status_code=code)

    @app.post("/v1/batches/bulk")
    async def post_bulk(request: Request):
        failed = chaos_response()
        if failed is not None:
            return failed
        payload = await request.json()
        batches = payload.get("batches", [])
        if len(batches) > BULK_MAX:
            return JSONResponse({"error": "invalid", "detail": "more than 50"}, status_code=422)
        results = []
        for b in batches:
            code, body = state.check_batch(b)
            seq = b.get("seq") if isinstance(b, dict) else None
            if code == 200:
                results.append({"seq": seq, "status": body["status"]})
            else:
                results.append({"seq": seq, "status": "error", "error": body.get("error", "invalid")})
        return {"results": results}

    @app.post("/v1/heartbeat")
    async def post_heartbeat(request: Request):
        failed = chaos_response()
        if failed is not None:
            return failed
        hb = await request.json()
        meter = hb.get("meter_id")
        if meter not in state.keys:
            return JSONResponse({"error": "unknown_meter"}, status_code=404)
        if not verify_fields(state.keys[meter], hb):
            return JSONResponse({"error": "bad_signature"}, status_code=401)
        with state.lock:
            state.heartbeats.append(hb)
        return {"ok": True, "server_time": _now()}

    @app.post("/_chaos")
    async def set_chaos(request: Request):
        body = await request.json()
        with state.lock:
            for k in ("fail_rate", "latency_ms", "down"):
                if k in body:
                    state.chaos[k] = body[k]
            return dict(state.chaos)

    @app.post("/_reset")
    def reset():
        state.reset()
        return {"ok": True}

    @app.get("/_stored")
    def stored_count():
        with state.lock:
            return {"count": len(state.stored)}

    return app


app = create_app()
