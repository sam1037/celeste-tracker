# PyInstaller spec for the desktop app (doc/DESIGN.md, step 7). Build on the OS you build for:
#   uv run --group build --extra desktop pyinstaller packaging/celeste-tracker.spec --noconfirm
# Windows: dist/CelesteTracker/CelesteTracker.exe (a folder: starts faster and trips antivirus less than one file).
# macOS:   dist/Celeste Tracker.app (unsigned).
import sys
from pathlib import Path

root = Path(SPECPATH).parent
icon = str(root / "celeste_tracker/web/static/icon.png")  # also the page's favicon; PyInstaller makes the .ico/.icns with Pillow

a = Analysis(
    [str(root / "celeste_desktop.py")],
    pathex=[str(root)],
    # server.py finds the page next to itself, so it goes in the same place inside the build
    datas=[(str(root / "celeste_tracker/web/static"), "celeste_tracker/web/static")],
    excludes=["pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CelesteTracker", console=False, icon=icon,
          upx=False)  # UPX-packed exes get flagged by antivirus far more often
coll = COLLECT(exe, a.binaries, a.datas, name="CelesteTracker", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(coll, name="Celeste Tracker.app", bundle_identifier="io.github.sam1037.celeste-tracker", icon=icon,
                 info_plist={"NSHighResolutionCapable": True})
