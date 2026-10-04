"""Finding the Saves and Mods folders, the save slots, and the config file."""
import os
import re
import sys
import tomllib
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


def find_saves_dir(saves=None):
    """The Saves folder: the given one, else the first default for this OS that exists."""
    if saves:
        return Path(saves)
    return next((d for d in default_saves_dirs() if d.is_dir()), None)


def find_save(file=None, saves=None, slot=0):
    if file:
        return Path(file)
    d = find_saves_dir(saves)
    p = d / f"{slot}.celeste" if d else None
    if p and p.exists():
        return p
    sys.exit("Could not find the save file. Use --saves <folder> or --file <path>.")


def list_slots(saves_dir):
    """[(slot number, path)] for every N.celeste in the folder (not settings, debug or mod side files)."""
    slots = [(int(p.stem), p) for p in Path(saves_dir).iterdir() if re.fullmatch(r"\d+\.celeste", p.name)]
    return sorted(slots)


def mods_dir_for(save_path, mods_arg):
    """The Mods folder: next to Saves for 'auto', else the given path."""
    return Path(save_path).parent.parent / "Mods" if mods_arg == "auto" else Path(mods_arg)


# ---------------------------------------------------------------- user data folder and config

def data_dir():
    """Where the tracker keeps its own files (config now, the SQLite store later)."""
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "celeste-tracker"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/celeste-tracker"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "celeste-tracker"


def config_path():
    return data_dir() / "config.toml"


def load_config(path):
    """{'saves': ..., 'mods': ...} from config.toml, {} if there is none."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"{path} is not valid TOML ({e}). Fix or delete it and run again.")


def write_config(path, values):
    """Write string values as TOML (tomllib can only read)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    esc = lambda v: str(v).replace("\\", "\\\\").replace('"', '\\"')
    path.write_text("".join(f'{k} = "{esc(v)}"\n' for k, v in values.items() if v), encoding="utf-8")
