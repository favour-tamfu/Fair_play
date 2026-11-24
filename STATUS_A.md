# STATUS A — updated 2026-11-24 00:35
Current task: MC1 prep (A side)
Done: A-T00, A-T01, A-T02 (file input; mic music check still open), A-T03 signing switched to fairplay_core, A-T06 minimal runner, A-T08 netcheck script, cp1_a script
Next up: uploader chaos tests (A-T05), then joint MC1 with B
Next merge checkpoint: MC1 — waiting on B's ingest API and hotspot
Blockers: A-T02 mic check (music vs silence not separated yet); B not ready for MC1
Open requests to B: MC1 hotspot port 8000 open and /health ok
Health: pytest core device -> 193 passed; e2e 25 s clip -> 2 windows stored by fake server; netcheck (local) GREEN
Local-only: all commits since 4615239 not pushed
