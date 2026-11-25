# Fair Play meter for Windows (FairPlayMeter.exe)

The listener packaged as one folder with `FairPlayMeter.exe`. Python is not needed on the bar's laptop.

## Build (Laptop A, repo root)
```
.\device\packaging\build.ps1
```
Makes `dist\FairPlayMeter\` and `dist\FairPlayMeter_windows.zip` (about 50 MB). The build holds no key, config,
state or audio; `dist\` is a build output and is not committed.

## Use on a bar laptop
1. Unzip `FairPlayMeter_windows.zip` anywhere (e.g. `C:\FairPlay`).
2. Double-click `FairPlayMeter.exe` (or run `FairPlayMeter.exe setup`). Enter the meter id and venue id that SONACAM gave,
   and the SONACAM address. It makes this meter's private key in `device\secrets\` and prints the public key.
3. Register the public key on the SONACAM admin page (Register meter key).
4. `FairPlayMeter.exe check` lists the microphones (the default one has a `*`) and checks that SONACAM answers.
5. Double-click `FairPlayMeter.exe` again: it listens to the default microphone and sends signed fingerprints.
   Ctrl+C stops it; anything not yet sent stays in `device\state\` and goes out on the next start.

Options: `FairPlayMeter.exe run --input file:C:\path\song.wav` (play a file instead of the microphone),
`--mode field` (one 10-second window per minute instead of continuous demo mode), `setup --force` (new key).

## Keep private
`device\secrets\<meter>.seed` is the meter's signing key. Never copy it to another machine or share it; a new laptop
gets its own key with `setup`, and the old key is removed on the SONACAM admin page.

## Tested (Laptop A, 2026-11-25)
- Built with PyInstaller 6.11.1 from `.venv` (Python 3.11).
- Clean folder: `setup` made key, config and public key; `check` listed the microphones;
  `run --input file:tone_mix.wav` against the fake SONACAM (device/tools/fake_sonacam.py) → 1 window made,
  signature verified, `acked: stored`.
- Not yet tested: a live microphone run against B's real server.
