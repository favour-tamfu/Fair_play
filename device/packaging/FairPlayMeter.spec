# PyInstaller spec for the Windows meter: ONE file, dist\FairPlayMeter.exe (copy just that file to a bar laptop).
# Build from the repo root with .\device\packaging\build.ps1 [-Url https://<SONACAM address>]
# No keys, configs, state or audio are bundled: each meter makes its own key on first run, next to the .exe.
# The only optional extra is sonacam_url.txt (the default SONACAM address), written by build.ps1 under build\ (not git).
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))       # repo root (SPECPATH = folder of this file)
CORE = os.path.join(ROOT, "core")                                 # fairplay_core (an editable install)
sys.path[:0] = [ROOT, CORE]
os.environ["PYTHONPATH"] = os.pathsep.join([ROOT, CORE, os.environ.get("PYTHONPATH", "")])

hidden = (collect_submodules("device.agent") + collect_submodules("device.tools") + collect_submodules("fairplay_core")
          + ["tomli_w", "nacl.signing"])

datas = []
url_file = os.environ.get("FAIRPLAY_URL_FILE", "")
if url_file and os.path.isfile(url_file):
    datas.append((url_file, "."))

a = Analysis(
    [os.path.join(SPECPATH, "meter_app.py")],
    pathex=[ROOT, CORE],
    hiddenimports=hidden,
    datas=datas,
    excludes=["fastapi", "uvicorn", "pytest", "jsonschema", "tkinter", "matplotlib", "pandas", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="FairPlayMeter", console=True, upx=False,
          runtime_tmpdir=None)
