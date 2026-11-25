# Fair Play meter for Windows (FairPlayMeter.exe)

The listener packaged as ONE file, `FairPlayMeter.exe`. Python is not needed on the bar's laptop. No questions are asked.

## Build (Laptop A, repo root)
```
.\device\packaging\build.ps1 -Url https://<SONACAM address>
```
Makes `dist\FairPlayMeter.exe`. `-Url` builds the SONACAM address into the exe (written under `build\`, never into git);
without it the default is the LAN server. The build holds no key, config, state or audio.

## Use on a bar laptop
1. Copy `FairPlayMeter.exe` into its own folder (e.g. `C:\FairPlay`) and double-click it.
2. First start: it sets itself up (its own key, a free meter id such as `M-4821`, the bar and the address built in)
   and shows **Waiting for approval from SONACAM** with the meter id and a key fingerprint (e.g. `84f9 2b00 1b6a d4ce`).
3. SONACAM opens the operations page: **Meters > Waiting for approval** lists the meter, the computer name and the same
   fingerprint. Approve (click twice) or Reject. Until it is approved its reports are refused.
4. Once approved the meter starts listening in the background and shows a menu:
   `1 Status` · `2 Pause/Resume listening` · `3 Check the connection to SONACAM` · `4 Meter details` · `5 Stop and close`.
   Next time, double-click goes straight to listening (approval is remembered; works offline, samples wait and are sent later).

If the id is already used by another meter, the meter takes another id by itself. With an older SONACAM server (no
join step) it waits the same way and says to register `contract\meters\<id>.pub.json` under Operations > Register a meter.
Options: `FairPlayMeter.exe check` (microphones, connection, approval), `run --input file:C:\path\song.wav` (needs ffmpeg
for mp3), `run --mode field` (one 10-second window per minute), `setup --meter M-xx --force` (by hand, normally not needed).

## Keep private
`device\secrets\<meter>.seed` is the meter's signing key. Never copy the meter's folder to another machine: copy only
the exe, and each laptop makes its own key. A meter that is not needed any more is retired on the operations page.

## Tested (Laptop A, 2026-11-25)
- `device/tests/test_meter_join.py` (8): setup asks nothing; the join request is signed with the meter's own key; waits
  through pending and remembers approval; stops on reject; takes a new id when its id is taken; an older server is asked
  through the signed heartbeat; the menu listens in the background, pauses, resumes, shows details and stops cleanly.
- The built exe, double-clicked in an empty folder against the public server: set itself up and showed the waiting
  screen; the request reached SONACAM's waiting list.
- Server side `server/tests/test_meter_join.py` needs Postgres (Laptop B).
