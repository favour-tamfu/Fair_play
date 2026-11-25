# Fair Play online — shared deployment plan (Person A + Person B)

Goal: the SONACAM server (API, workers, Postgres, web pages) is reachable on the internet at a public **HTTPS** address,
and listeners (FairPlayMeter.exe) send their signed batches there instead of over the LAN. Both laptops follow this plan.
Revised 2026-11-25 by A: **no bank cards** → no Oracle/Google/AWS VMs; free options that need no card only. Request R-032.

**Decision (Person A, 2026-11-25): tunnelling, for the demo only.** Fair Play is meant for a government body: in real use SONACAM
runs this same stack on its own servers (the docker compose file is the install). For the hackathon, Laptop B plays SONACAM's
server and a tunnel gives it a public HTTPS address.

## 1. What we are serving (facts from the repo)
- B's `docker compose` stack on Laptop B: `api` (uvicorn, serves `web/`, the live feed over SSE, sign-in with session cookies),
  4 workers (`worker_fp`, `worker_match` with the fingerprint index **in memory**, `worker_play`, `scheduler`) and **Postgres 16**.
- Meters call `POST /v1/batches`, `/v1/batches/bulk`, `/v1/heartbeat`; pages call `/api/v1/...` on the same address.

## 2. Choice (free, no card)
| Option | Verdict | Why |
|---|---|---|
| **Tailscale Funnel** on Laptop B (`https://<laptop>.<tailnet>.ts.net`) | **Chosen** | Free personal plan, sign-in with Google/GitHub/Microsoft (no card). One command publishes port 8000 over HTTPS with a **stable** name. B's stack runs unchanged; nothing to migrate. Funnel is beta and its streaming limits aren't published: test the live feed (step 3). |
| **Cloudflare quick tunnel** (`cloudflared tunnel --url http://localhost:8000` → `https://<random>.trycloudflare.com`) | **Backup 1** | No account, no card, one command. But: **no server-sent events** (the dashboard's instant feed stops; the dashboard still refreshes its figures every 30 s), and **a new address each time it starts** (re-point the meters: edit `sonacam_url`, restart). Keep it running for the whole demo. A *named* Cloudflare tunnel fixes both but needs our own domain on Cloudflare. |
| **ngrok** free static domain (`https://<name>.ngrok-free.app`) | **Backup 2** | Free account, no card, one command, fixed address, streams the live feed. Free plan shows a one-time warning page to browser visitors (meters and API calls are not affected). |
| Render / Koyeb / Back4App free containers | Rejected | 512 MB or less, no free background workers, sleep when idle: our 4 workers + in-memory index don't fit without rewriting B's server. |
| Oracle / Google Cloud / AWS free VMs | Rejected | Need a bank card. |
| Hugging Face Spaces (Docker) | Rejected | Docker Spaces on the free CPU tier appear to need a paid plan since mid-2026. |
| Cloudflare Pages + Workers (no tunnel) | Not now | Free and no card, but can't run our Python server; would need a relay Worker plus a collect-and-publish loop on B — hours of new code. Containers on Cloudflare need the paid plan. |

**The trade-off:** the server is Laptop B. It must stay **on, plugged in, awake and online** during the demo
(Settings → Power → Screen and sleep: Never; Docker Desktop running; a stable connection, ideally not the same phone hotspot
that the room uses). If B's laptop goes offline, the site and the meters' uploads pause; meters keep their batches in the outbox
and send them when it's back.

## 3. Steps (owner in brackets)

### Step 1 — Publish B's server (B, 10 min)
1. Install Tailscale for Windows (tailscale.com/download), sign in (Google/GitHub/Microsoft account; free).
2. Make sure the stack runs: `docker compose up -d` → `http://localhost:8000` works.
3. In PowerShell (admin): `tailscale funnel --bg 8000`. The first time it opens a page to approve Funnel for the tailnet — approve.
4. `tailscale funnel status` shows `https://<laptop>.<tailnet>.ts.net` → that is **the address**. Share it in the team chat.
5. Phone on **mobile data**: open the address → landing loads; sign in to the SONACAM app → dashboard; watch the live feed 2 minutes.
6. If 5 fails: backup 1 — install cloudflared (`winget install --id Cloudflare.cloudflared`), run
   `cloudflared tunnel --url http://localhost:8000`, use the printed `https://….trycloudflare.com` (no live feed; new address each start).
   Backup 2 — install ngrok, `ngrok config add-authtoken <token>`, claim the free static domain in
   the ngrok dashboard, `ngrok http --url=<name>.ngrok-free.app 8000`; the address is `https://<name>.ngrok-free.app`.

### Step 2 — Point the listener at it (A, 10 min + rebuild)
1. A sets `DEFAULT_SONACAM` in `device/packaging/meter_app.py` to the address and rebuilds (`.\device\packaging\build.ps1`).
   Existing meters: edit `sonacam_url` in `device\config\<meter>.toml` (no rebuild needed).
2. Each listening laptop: unzip, `FairPlayMeter.exe setup` (meter id, venue id; the address is pre-filled), then register the
   printed public key on the operations page (`/sonacam-x7k2q9-admin.html` → Register a meter; SONACAM sign-in).
3. `FairPlayMeter.exe check` → "SONACAM … answers (HTTP 200)" → run. Batches go out over HTTPS; the outbox holds them during drops.

### Step 3 — End-to-end test over the internet (A + B, 20 min)
- Phone on mobile data: landing, artist ranking, artist portal sign-in, SONACAM dashboard and operations at the address.
- Play a catalogue song near a meter: the play appears on the dashboard feed, map and chart within ~30 s.
- Tamper test (B): change one play → dashboard turns red within 1 s → restore.
- Leave a meter running 30 min: no dead/parked batches; window times match real time.

## 4. Safety on the public internet
- The SONACAM sign-in password (= `ADMIN_TOKEN` in Laptop B's `.env`) must be strong and shared only privately; never in git.
- Postgres stays private (compose binds it to 127.0.0.1); only port 8000 is published through the tunnel.
- Meters can only send batches signed with a registered key (D-020). No audio is served.
- Stop publishing after the hackathon: `tailscale funnel --bg off` (or stop ngrok).

## 5. Who does what
| Step | A | B |
|---|---|---|
| 1 Publish | — | Tailscale Funnel (or ngrok), share the address |
| 2 Listener | rebuild exe with the address; register keys | share the sign-in privately |
| 3 Test | phone test, meter run | tamper test, keep the laptop awake |

Status: **plan only — nothing published yet.**
