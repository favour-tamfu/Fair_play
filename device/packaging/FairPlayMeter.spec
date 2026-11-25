# PyInstaller spec for the Windows meter (one folder: dist\FairPlayMeter\FairPlayMeter.exe).
# Build from the repo root:  .\.venv\Scripts\pyinstaller device\packaging\FairPlayMeter.spec --noconfirm
# No keys, configs, state or audio are bundled: each meter makes its own key on first run.
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))       # repo root (SPECPATH = folder of this file)
CORE = os.path.join(ROOT, "core")                                 # fairplay_core (an editable install)
sys.path[:0] = [ROOT, CORE]
os.environ["PYTHONPATH"] = os.pathsep.join([ROOT, CORE, os.environ.get("PYTHONPATH", "")])

hidden = (collect_submodules("device.agent") + collect_submodules("device.tools") + collect_submodules("fairplay_core")
          + ["tomli_w", "nacl.signing"])

a = Analysis(
    [os.path.join(SPECPATH, "meter_app.py")],
    pathex=[ROOT, CORE],
    hiddenimports=hidden,
    excludes=["fastapi", "uvicorn", "pytest", "jsonschema", "tkinter", "matplotlib", "pandas", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FairPlayMeter", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="FairPlayMeter")
