# Fair Play online — shared deployment plan (Person A + Person B)

Goal: the SONACAM server (API, workers, Postgres, web pages) runs on a free cloud machine at a public **HTTPS** address;
listeners (FairPlayMeter.exe) send their signed batches there over the internet instead of the LAN. Both laptops follow
this one plan. Written by A on 2026-11-25 01:58; B reviews (request R-023). Deadline: demo Wed 25 Nov 12:00.

## 1. What we are hosting (facts from the repo)
- One Docker image, **five processes**: `api` (uvicorn, also serves `web/` and the live feed over SSE), `worker_fp`,
  `worker_match` (keeps the whole fingerprint index **in memory**), `worker_play`, `scheduler`; plus **Postgres 16**.
- Settings come from `.env`: `POSTGRES_*`, `DATABASE_URL`, `ADMIN_TOKEN` (D-020), `SERVE_WEB`.
- Meters talk to `POST /v1/batches`, `/v1/batches/bulk`, `/v1/heartbeat`; pages call `/api/v1/...` on the same address.

## 2. Choice of host (free) and why
| Option | Verdict | Why |
|---|---|---|
| **Oracle Cloud "Always Free" VM** (Ampere ARM, up to 4 CPU / 24 GB RAM, 200 GB disk) | **Chosen** | Runs our `docker compose` **unchanged** (5 processes + Postgres + in-memory index fit easily); free with no time limit. Needs a card at sign-up (identity check, not charged) and ARM capacity is sometimes "out of capacity" in a region (retry or pick another home region). |
| B's laptop + **Tailscale Funnel** (`https://<laptop>.<tailnet>.ts.net`) | **Fallback, set up first** (10 min) | No code or hosting change; stable HTTPS name; free. But the laptop must stay on, awake and online; Funnel is beta and its streaming limits aren't published (test the live feed). |
| Render / Koyeb free web service + Neon free Postgres | Rejected | 512 MB RAM, 0.1 CPU, no free background workers, sleeps after 15 min: our 4 workers and in-memory index don't fit without rewriting B's server. |
| Hugging Face Spaces (Docker) | Rejected | Docker Spaces on the free CPU tier appear to need a paid plan since mid-2026; disk is wiped on restart. |
| Cloudflare quick tunnel (trycloudflare) | Rejected | Does **not** support server-sent events (our live feed); URL changes every start. |
| Fly.io / Railway | Rejected | No lasting free tier (trial credit only). |

HTTPS on the VM: **Caddy** (one extra container) gets a free Let's Encrypt certificate automatically for the name
`<public-ip-with-dashes>.sslip.io` (no domain purchase, no DNS setup). If Let's Encrypt refuses that name, use a free
DuckDNS name instead (`fairplay-cm.duckdns.org`, set once on duckdns.org).

## 3. The plan, step by step (owner in brackets)

### Step 0 — Fallback first, so the demo is safe whatever happens (B, 10 min)
1. Install Tailscale on Laptop B, sign in (free personal account).
2. `tailscale funnel --bg 8000` → note the `https://….ts.net` address. Open it on a phone on mobile data: landing page loads.
3. Open the dashboard there and watch the live feed for 2 minutes (checks SSE through Funnel).
4. Post the address in the team chat. **A** can already point a meter at it (Step 4) and test.

### Step 1 — Create the free VM (A or B, 20 min, the only clicking)
1. Sign up at cloud.oracle.com (Always Free). Home region: one with Ampere capacity (e.g. Frankfurt, Johannesburg if offered).
2. Create instance: shape **VM.Standard.A1.Flex**, 4 OCPU, 24 GB; image **Ubuntu 24.04**; paste A's SSH public key
   (or let it generate one and save it); in "Advanced → Management → cloud-init", paste `deploy/cloud-init.yaml`
   (it installs Docker and the firewall rules on first boot — no manual server setup).
3. In the VM's subnet **Security List**, add ingress rules for TCP **80** and **443** from `0.0.0.0/0`.
4. Note the public IP → the address is `https://<ip with dots replaced by dashes>.sslip.io`.

### Step 2 — Put the server on the VM (B, 20 min)
1. B pushes/merges so the VM can pull: `main` with a/work merged (REQUESTS.md conflict: keep both sides, renumber A's R-019/R-020 to R-021/R-022).
2. On the VM (one SSH session): `git clone https://github.com/favour-tamfu/Fair_play.git && cd Fair_play`.
3. `.env` from `.env.example`: strong `POSTGRES_PASSWORD`, strong `ADMIN_TOKEN` (`python3 -c "import secrets;print(secrets.token_urlsafe(24))"`),
   `SERVE_WEB=1`, and `SITE_ADDRESS=<ip-with-dashes>.sslip.io`. Never commit `.env`.
4. `docker compose -f docker-compose.yml -f deploy/docker-compose.cloud.yml up -d --build`
   (the override adds Caddy for HTTPS and stops publishing port 8000 to the internet).

### Step 3 — Move B's data, not re-create it (B, 15 min)
The catalogue (183 songs, fingerprints), meter keys and mock month already live in B's database. Copy it instead of
re-uploading audio:
1. Laptop B: `docker compose exec db pg_dump -U fairplay -Fc fairplay > fairplay.dump`
2. Copy to the VM: `scp fairplay.dump ubuntu@<ip>:~/Fair_play/`
3. VM: `docker compose exec -T db pg_restore -U fairplay -d fairplay --clean --if-exists < fairplay.dump`, then
   `docker compose restart worker_match` (reloads the index). Audio files are not needed on the server for matching.
4. Check: `https://<address>/api/v1/overview` shows songs_ready = 183.

### Step 4 — Point the listener at the server (A, 10 min + rebuild)
1. A sets the default address in `device/packaging/meter_app.py` (`DEFAULT_SONACAM`) to the HTTPS address and rebuilds
   (`.\device\packaging\build.ps1`). For the existing M-07 config just edit `sonacam_url` in `device\config\M-07.toml`.
2. On each listening laptop: unzip, `FairPlayMeter.exe setup` (meter id, venue id; address pre-filled), then register the printed
   public key on the hosted admin page (`/sonacam-x7k2q9-admin.html`, needs the ADMIN_TOKEN from B).
3. `FairPlayMeter.exe check` → "SONACAM … answers (HTTP 200)"; then run. Batches go out over HTTPS; the outbox keeps them
   during network drops and sends them later.

### Step 5 — End-to-end test over the internet (A + B, 20 min)
- From a phone on mobile data: landing, Artists, portal, dashboard load at the HTTPS address.
- Play a catalogue song near the meter: within ~30 s the play appears on the dashboard feed, map and chart.
- Tamper test (B): change one play in the DB → dashboard turns red within 1 s → restore.
- Leave the meter running 30 min: no "dead" or "parked" batches; window times match real time (keep Laptop A awake —
  the clock-drift bug B reported in their R-020 is still open).

## 4. Safety on the public internet
- `ADMIN_TOKEN` set and kept out of git; share it only by private message. Postgres is never published (compose binds it to 127.0.0.1).
- Meters can only send batches signed with a registered key; unregistered keys are refused (D-020).
- The dashboard's secret address hides it but does not protect it (no login); fine for the demo, say so if asked.
- Album covers and song titles are public on the site; no audio is served.

## 5. Who does what (summary)
| Step | A | B |
|---|---|---|
| 0 Fallback (Funnel) | test a meter against it | set up, share the address |
| 1 VM | create account/VM if B is busy | or create it |
| 2 Server on VM | — | clone, .env, compose up |
| 3 Data | — | pg_dump → pg_restore |
| 4 Listener | rebuild exe with the address, register keys | share ADMIN_TOKEN privately |
| 5 Test | phone test, meter run | tamper test, watch logs |

## 6. Files in this folder
- `deploy/cloud-init.yaml` — first-boot setup of the VM (Docker, firewall). Not yet run.
- `deploy/docker-compose.cloud.yml` — adds Caddy (HTTPS) on top of B's compose file. Not yet run.
- `deploy/Caddyfile` — Caddy's two-line config (reverse proxy to `api:8000`, live feed streamed unbuffered).

Status: **plan only — nothing deployed yet; the cloud files are untested.**
