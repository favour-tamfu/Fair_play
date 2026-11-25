# Fair Play meter for Windows (FairPlayMeter.exe)

The listener packaged as ONE file, `FairPlayMeter.exe`. Python is not needed on the bar's laptop.

## Build (Laptop A, repo root)
```
.\device\packaging\build.ps1 -Url https://<SONACAM address>
```
Makes `dist\FairPlayMeter.exe` (one file). `-Url` sets the default SONACAM address inside the exe (written under `build\`,
never into git); without it the default is the LAN server. The build holds no key, config, state or audio.

## Use on a bar laptop
1. Copy `FairPlayMeter.exe` into its own folder (e.g. `C:\FairPlay`). Everything it makes stays next to it.
2. Double-click it. Enter the meter id SONACAM gave (e.g. `M-22`), the bar id and the address (Enter keeps the defaults).
   It makes this meter's private key, asks SONACAM to join and shows the key fingerprint, e.g. `3f2a 91c0 7b4e d215`.
3. SONACAM opens the operations page: **Meters > Waiting for approval** shows the meter, its bar, the computer name and
   the same fingerprint. Approve (or Reject) it. Until it is approved the meter does not count: its reports are refused.
4. The meter checks every 15 s and starts listening as soon as it is approved. Next time, double-click starts it directly.
   Ctrl+C stops it; anything not yet sent stays in `device\state\` and goes out on the next start.

`FairPlayMeter.exe check` lists the microphones, checks that SONACAM answers and shows the approval status.
Options: `FairPlayMeter.exe run --input file:C:\path\song.wav` (needs ffmpeg for mp3), `--mode field` (one 10-second
window per minute instead of continuous demo mode), `setup --force` (new key, or another meter id).
The manual way still works: register `contract\meters\<id>.pub.json` under Operations > Register a meter.

## Keep private
`device\secrets\<meter>.seed` is the meter's signing key. Never copy the meter's folder to another machine: copy only
the exe, and each laptop makes its own key. A meter that is not needed any more is retired on the operations page.

## Tested (Laptop A, 2026-11-25)
- Unit tests `device/tests/test_meter_join.py`: the join request is signed with the meter's own key and carries no
  secret; the meter waits through "pending", starts on "approved", stops on "rejected" or a taken id, starts anyway
  when SONACAM is unreachable (reports wait) or has no join step yet.
- Server side `server/tests/test_meter_join.py` needs Postgres (Laptop B).
