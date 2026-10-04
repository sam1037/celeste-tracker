"""Finding the Saves and Mods folders."""
import os
import sys
from pathlib import Path


def default_saves_dirs():
    home = Path.home()
    c = []
    if sys.platform.startswith("win"):
        for pf in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if pf:
                c.append(Path(pf) / "Steam/steamapps/common/Celeste/Saves")
        c.append(Path(os.environ.get("LOCALAPPDATA", home)) / "Celeste/Saves")
    elif sys.platform == "darwin":
        c.append(home / "Library/Application Support/Celeste/Saves")
        c.append(home / "Library/Application Support/Steam/steamapps/common/Celeste/Celeste.app/Contents/Resources/Saves")
    else:
        c.append(home / ".local/share/Celeste/Saves")
        c.append(home / ".steam/steam/steamapps/common/Celeste/Saves")
        c.append(home / ".local/share/Steam/steamapps/common/Celeste/Saves")
    return c


def find_save(file=None, saves=None, slot=0):
    if file:
        return Path(file)
    dirs = [Path(saves)] if saves else default_saves_dirs()
    for d in dirs:
        p = d / f"{slot}.celeste"
        if p.exists():
            return p
    sys.exit("Could not find the save file. Use --saves <folder> or --file <path>.")


def mods_dir_for(save_path, mods_arg):
    """The Mods folder: next to Saves for 'auto', else the given path."""
    return save_path.parent.parent / "Mods" if mods_arg == "auto" else Path(mods_arg)
