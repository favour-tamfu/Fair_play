"""Locked constants shared by device and server. Change only via contract change (see docs/02 §6)."""
FP_VERSION = "fp-1.0"
SCHEMA_VERSION = 1

SAMPLE_RATE = 8000          # Hz, after resampling
CAPTURE_RATE = 48000        # Hz, laptop mic capture (resample_poly up=1, down=6)
N_FFT = 512
HOP = 256
BIN_MIN = 7                 # ~109 Hz
BIN_MAX = 224               # ~3500 Hz (inclusive)
PEAK_NEIGHBORHOOD = (21, 31)   # (frames, bins) for maximum_filter
THRESH_NEIGHBORHOOD = (63, 31) # (frames, bins) for uniform_filter
THRESH_DB = 6.0
BLOCK_FRAMES = 32
PEAKS_PER_BLOCK = 30
MAG_OFFSET_DB = 80.0        # mag_u8 = clip(round(2*(mag_db + 80)), 0, 255)
MAG_SCALE = 2.0

WINDOW_S = 10               # seconds per analysis window
WINDOW_SAMPLES = WINDOW_S * SAMPLE_RATE   # 80000
FRAMES_PER_WINDOW = 1 + (WINDOW_SAMPLES - N_FFT) // HOP   # 311

FANOUT = 5
DT_MIN, DT_MAX = 1, 63      # frames
DF_MAX = 63                 # bins
MATCH_MIN_ALIGNED = 8
MATCH_RATIO = 2.0

FRAME_S = HOP / SAMPLE_RATE  # 0.032 s
