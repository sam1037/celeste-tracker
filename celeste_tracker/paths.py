"""Finding the Saves and Mods folders, the save slots, and the config file."""
import json
import os
import re
import sys
import tomllib
from pathlib import Path


# ---------------------------------------------------------------- finding the Celeste folder
# For players who never pass --saves: the desktop app has to find the game by itself. Everything here only reads.

def olympus_config_files():
    """Where Olympus (Everest's installer) keeps config.json, which lists the Celeste installs it manages.
    The Windows path is verified on the author's PC; the macOS and Linux ones are inferred."""
    home = Path.home()
    if sys.platform.startswith("win"):
        return [Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Olympus/config.json"]
    if sys.platform == "darwin":
        return [home / "Library/Application Support/Olympus/config.json"]
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [xdg / "Olympus/config.json", home / ".local/share/Olympus/config.json"]


def olympus_installs(files=None):
    """Celeste folders from Olympus's config.json ({"installs": [{"path": ...}, ...]}), in its order."""
    found = []
    for f in olympus_config_files() if files is None else files:
        try:
            installs = json.loads(Path(f).read_text(encoding="utf-8")).get("installs") or []
        except (OSError, ValueError, AttributeError):
            continue
        found += [Path(i["path"]) for i in installs if isinstance(i, dict) and isinstance(i.get("path"), str)]
    return found


def steam_roots():
    """Steam's own folder: from the registry on Windows, else the usual places."""
    home = Path.home()
    roots = []
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
        roots += [Path(pf) / "Steam" for pf in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"))
                  if pf]
    elif sys.platform == "darwin":
        roots.append(home / "Library/Application Support/Steam")
    else:
        roots += [home / ".steam/steam", home / ".local/share/Steam",
                  home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]  # Flatpak
    return roots


def steam_libraries(root):
    """Every Steam library folder: the root itself plus the ones in steamapps/libraryfolders.vdf (other drives)."""
    libs = [Path(root)]
    try:
        vdf = (Path(root) / "steamapps/libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return libs
    libs += [Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    return libs


def celeste_dirs():
    """Celeste install folders this computer may have, most likely first, not checked to exist: Olympus's
    installs, the Steam libraries, then the usual Epic and itch folders."""
    dirs = olympus_installs()
    for root in steam_roots():
        dirs += [lib / "steamapps/common/Celeste" for lib in steam_libraries(root)]
    if sys.platform.startswith("win"):
        for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if pf:
                dirs.append(Path(pf) / "Epic Games/Celeste")
        dirs.append(Path(os.environ.get("APPDATA", Path.home())) / "itch/apps/celeste")
    seen, unique = set(), []
    for d in dirs:
        key = os.path.normcase(str(d))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def saves_in(folder):
    """The Saves folder for a folder a player points at: the Saves folder itself, or a Celeste folder holding one
    (also inside a macOS Celeste.app). None if there is none."""
    folder = Path(folder)
    for d in (folder, folder / "Saves", folder / "Contents/Resources/Saves", folder / "Celeste.app/Contents/Resources/Saves"):
        if d.is_dir() and (d.name == "Saves" or list_slots(d)):
            return d
    return None


def default_saves_dirs():
    home = Path.home()
    c = [d / "Saves" for d in celeste_dirs()]  # on Windows the game keeps its saves in its own folder
    if sys.platform.startswith("win"):
        c.append(Path(os.environ.get("LOCALAPPDATA", home)) / "Celeste/Saves")
    elif sys.platform == "darwin":
        c.append(home / "Library/Application Support/Celeste/Saves")
        c.append(home / "Library/Application Support/Steam/steamapps/common/Celeste/Celeste.app/Contents/Resources/Saves")
    else:
        c.append(Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "Celeste/Saves")
    return c


def find_saves_dir(saves=None, candidates=None):
    """The Saves folder: the given one, else the first default that has save slots, else the first that exists."""
    if saves:
        return Path(saves)
    dirs = [d for d in (default_saves_dirs() if candidates is None else candidates) if d.is_dir()]
    return next((d for d in dirs if list_slots(d)), dirs[0] if dirs else None)


def find_mods_dir(saves_dir, mods=None):
    """The Mods folder: the given one, else Everest's next to Saves, else one in a known Celeste folder."""
    if mods and mods != "auto":
        return Path(mods)
    for d in [Path(saves_dir).parent] + celeste_dirs():
        if (d / "Mods").is_dir():
            return d / "Mods"
    return None


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
