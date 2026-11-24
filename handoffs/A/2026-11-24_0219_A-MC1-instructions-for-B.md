# MC1 instructions for B — 2026-11-24 02:19 — from Person A / Laptop A

Goal: the joint MC1 test (docs/02 section 7, MC1 row). Read it all before you start.

## 1. Merge (B is merge captain)
    git fetch origin
    git checkout main
    git merge --no-ff origin/b/work
    git merge --no-ff origin/a/work
- A's branch is origin/a/work at 259d7d2 or later (the newest commit on it is A's MC1 prep).
- Conflicts can only be in README.md, DECISIONS.md, REQUESTS.md: keep both sides' text.
- Do NOT touch device/, web/, core/fairplay_core/peaks.py if they conflict; tell A instead.
- When green: git push origin main (only after step 3 passes).

## 2. Python environment (Laptop B)
    .\.venv\Activate.ps1  -> if blocked, run: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
    pip install -e core -r server\requirements.txt

## 3. Stack and firewall
    docker compose up -d
    curl.exe http://localhost:8000/health            # expect ok:true
    # admin PowerShell, once:
    .\scripts\firewall_b.ps1

## 4. Tell A your address on the shared network
    ipconfig
- Copy the IPv4 address of the adapter that is on the same network as Laptop A (Wi-Fi or hotspot).
- Send it to A. A puts it in device\config\M-07.toml as sonacam_url = "http://<that IP>:8000".
- Check from A: .\scripts\netcheck.ps1 -Url http://<that IP>:8000  must be GREEN.

## 5. Songs (3 of them, rights confirmed: CC0 or written consent)
- Put each file in data\songs\ on your laptop (git-ignored; never commit audio).
- Run the checkpoint with them:
    .\scripts\cp1_b.ps1 -Songs data\songs\<song1>.wav,data\songs\<song2>.wav,data\songs\<song3>.wav
- Expected last line: CP1 (B): GREEN. Keep the song IDs it prints (S-00000x).

## 6. Joint live test (both laptops)
1. B: watch accepted matches
       curl.exe -N http://localhost:8000/api/v1/feed
   Look for "event: match" lines with accepted true.
2. A: run the agent in demo mode:
       .\.venv\Scripts\python.exe -m device.agent run --config device\config\M-07.toml --mode demo --input mic
3. Someone plays one of the three songs on a speaker near A's laptop mic, for about 60 seconds.
4. PASS condition A: B shows accepted matches for at least 2 of the 3 songs.
5. Network cut: unplug or disable A's Wi-Fi for 2 minutes while A keeps running.
   A's status screen should show queued going up.
6. Restore the network. A's queued should go back to 0.
7. PASS condition B: no gaps in M-07 seq numbers (compare with A's last ack seq on its screen).
   Use B's own database check (names are in B's .env). Report the result.

## 7. Report back
- Write handoffs\B\<date>_B-MC1.md with: the cp1_b output, the match lines (song IDs, scores), the seq check result, and any errors.
- Append a short note to REQUESTS.md. Tell A which commit you merged into main.
- If anything fails, stop, write the failure into the handoff, and tell A. Do not change A's files.

## A's side (already done, for reference)
- .\scripts\cp1_a.ps1 -Url http://<B IP>:8000   runs A's tests, netcheck, then the agent in demo mode.
- A's last commit on a/work: 259d7d2.
