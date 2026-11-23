"""Mic check for Laptop A (A-T00 DoD).

Prints the audio devices, the default WASAPI input, records 3 s at 48 kHz
and prints the RMS level in dBFS. Clap near the laptop and the level should rise.

Run from the repo root with the venv active:
    python scripts/mic_check.py
"""
import math

import numpy as np
import sounddevice as sd

SR = 48000
SECONDS = 3


def wasapi_default_input():
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"]:
            idx = api.get("default_input_device", -1)
            if idx is not None and idx >= 0:
                return idx
    return None


def main():
    print("Audio devices:")
    print(sd.query_devices())
    dev = wasapi_default_input()
    if dev is None:
        dev = sd.default.device[0]
        print("No WASAPI default input found; using default input device.")
    print(f"Recording {SECONDS} s from device {dev} at {SR} Hz ...")
    try:
        audio = sd.rec(int(SECONDS * SR), samplerate=SR, channels=1, dtype="float32", device=dev)
        sd.wait()
    except sd.PortAudioError as exc:
        fallback = sd.default.device[0]
        print(f"Device {dev} failed ({exc}); retrying on default input {fallback}.")
        audio = sd.rec(int(SECONDS * SR), samplerate=SR, channels=1, dtype="float32", device=fallback)
        sd.wait()
    x = audio.reshape(-1)
    rms = float(np.sqrt(np.mean(np.square(x)) + 1e-12))
    dbfs = 20 * math.log10(rms + 1e-12)
    print(f"RMS level: {dbfs:.1f} dBFS (peak {float(np.max(np.abs(x))):.3f})")


if __name__ == "__main__":
    main()
