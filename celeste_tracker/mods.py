"""What the Mods folder knows that the save doesn't: map lists, sides and in-game titles.

Only zip file lists and each mod's Dialog/English.txt are read; nothing is loaded.
"""
import os
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path


def dkey(ident):
    """Dialog key for an ID: Everest swaps '/', ' ' and '-' for '_' (compared case-insensitively)."""
    return re.sub(r"[/ \-]", "_", ident).lower()


# Bump when read_mod()'s output changes, so zips cached by an older version (store.ModCache) are read again.
READ_VERSION = 2

DIALOG_KEY = re.compile(r"(\w+)\s*=(.*)")


def decode_text(raw):
    """A dialog file's text: UTF-8 (with or without a BOM), or UTF-16 when it starts with a UTF-16 BOM, which
    the game also reads (one mod in my Mods folder, Solaris, ships its English.txt as UTF-16)."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    return raw.decode("utf-8-sig", "replace")


def parse_dialog(raw):
    """A Dialog/English.txt as {lowercase key: value}. As in the game, a `key=` line starts a value and the
    lines after it that aren't keys continue it: Strawberry Jam puts every title on the line under its key
    (`StrawberryJam2021_5_Grandmaster_Hydro=`, then `  Shattersong`). Continued lines are joined with newlines.
    The first definition of a key wins."""
    out, key = {}, None
    for line in decode_text(raw).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = DIALOG_KEY.fullmatch(line)
        if m:
            key = m[1].lower()
            if key in out:  # defined again: keep the first value, and skip the lines that continue this one
                key = None
            else:
                out[key] = m[2].strip()
        elif key is not None:
            out[key] = f"{out[key]}\n{line}".strip()
    return out


def mod_name(raw):
    """The mod's name from its everest.yaml: the first top-level `Name:` (dependencies are indented deeper)."""
    m = re.search(r"^(?:-\s+|\s{1,3})Name:\s*(.+?)\s*$", raw.decode("utf-8-sig", "replace"), re.M)
    return m[1].strip("'\"") if m else ""


def split_side(path):
    """'Set/Map-B' -> ('Set/Map', 'B'). Everest loads <map>-B.bin and <map>-C.bin as that map's B and C sides;
    any other name (including '-D') is a map of its own, A side."""
    m = re.fullmatch(r"(.+)-([BC])", path)
    return (m[1], m[2]) if m else (path, "A")


@dataclass
class ModFiles:
    """One mod (zip or unzipped folder) that has maps."""
    id: str                     # everest.yaml Name, else the zip / folder name
    source: str                 # zip / folder name
    chapters: set = field(default_factory=set)  # SIDs of the chapters it owns


class ModInfo:
    """What the Mods folder knows that the save doesn't. Empty (all lookups blank) without --mods."""

    def __init__(self, maps=None, dialog=None, source=None, mods=None, owner=None):
        self.maps = maps or {}      # level set name -> {map SID: set of sides it has, e.g. {'A', 'B'}}
        self.dialog = dialog or {}  # lowercase dialog key -> text
        self.source = source
        self.mods = mods or {}      # mod ID -> ModFiles
        self.owner = owner or {}    # map SID -> ID of the mod whose zip holds it

    def sides(self, sid):
        """Sides a map has, e.g. 'ABC', '' if unknown."""
        return "".join(sorted(self.maps.get(sid.rpartition("/")[0], {}).get(sid, ())))

    def title(self, ident):
        """In-game title of a level set or map ID, '' if unknown."""
        text_ = self.dialog.get(dkey(ident), "")
        return re.sub(r"\s+", " ", re.sub(r"\{[^}]*\}", "", text_)).strip()

    def checkpoint(self, sid, room):
        return self.title(f"{sid}_{room}")

    def summary(self):
        return (f"{sum(len(v) for v in self.maps.values())} maps in {len(self.maps)} sets, "
                f"{len(self.dialog)} dialog keys")


def read_mod(names, read, source):
    """What one mod's files say: {'id', 'source', 'bins': [map paths], 'dialog': {...}}, or None if it has no maps."""
    bins = sorted(n[5:-4] for n in names if n.startswith("Maps/") and n.endswith(".bin"))
    if not bins:
        return None
    mod_id = next((mod_name(read(n)) for n in names if n.lower() in ("everest.yaml", "everest.yml")), "") or source
    dialog = {}
    for n in names:
        if n.lower() == "dialog/english.txt":
            for k, v in parse_dialog(read(n)).items():
                dialog.setdefault(k, v)
    return {"version": READ_VERSION, "id": mod_id, "source": source, "bins": bins, "dialog": dialog}


def stat_or_none(path):
    try:
        return path.stat()
    except OSError:
        return None


def read_zip(path):
    try:
        with zipfile.ZipFile(path) as z:
            orig = {n.replace("\\", "/"): n for n in z.namelist()}
            return read_mod(orig, lambda n: z.read(orig[n]), path.stem)
    except (OSError, zipfile.BadZipFile):
        return None


def read_folder(path):
    files = {p.relative_to(path).as_posix(): p for p in (path / "Maps").rglob("*.bin")}
    for extra in ("Dialog/English.txt", "everest.yaml", "everest.yml"):
        if (path / extra).is_file():
            files[extra] = path / extra
    return read_mod(files, lambda n: files[n].read_bytes(), path.name)


def scan_mods(mods_dir, cache=None):
    """Read map lists and English dialog from every mod (zip or unzipped folder) that has maps.

    cache (optional, see store.ModCache): get(path, size, mtime_ns) -> (hit, value), put(...), keep_only(paths).
    Zips that haven't changed since the last scan are taken from it instead of being opened again.
    """
    # Each file check over WSL's /mnt/c costs ~4 ms, and ~450 zips add up: scandir already knows which entries
    # are folders, and the stat calls and zip reads mostly wait on I/O, so they run on a thread pool.
    entries = sorted(os.scandir(mods_dir), key=lambda d: d.name)
    zips = [Path(d.path) for d in entries if not d.is_dir() and d.name.lower().endswith(".zip")]
    with ThreadPoolExecutor(16) as pool:
        stats = dict(zip(zips, pool.map(stat_or_none, zips)))
        zips = [z for z in zips if stats[z]]
        cached = {z: cache.get(str(z), stats[z].st_size, stats[z].st_mtime_ns) if cache else (False, None) for z in zips}
        # An entry from an older READ_VERSION counts as a miss (zips without maps are cached as None either way).
        cached = {z: (hit and (v is None or v.get("version") == READ_VERSION), v) for z, (hit, v) in cached.items()}
        misses = [z for z in zips if not cached[z][0]]
        read = dict(zip(misses, pool.map(read_zip, misses)))
    by_path = {}
    for z in zips:
        by_path[z] = cached[z][1] if cached[z][0] else read[z]
        if cache and not cached[z][0]:
            cache.put(str(z), stats[z].st_size, stats[z].st_mtime_ns, read[z])
    if cache:
        cache.keep_only([str(z) for z in zips])
    found = []
    for d in entries:  # in name order: the first mod to define a dialog key wins, as before
        path = Path(d.path)
        if d.is_dir():
            if (path / "Maps").is_dir():  # unzipped mods are few and change while being made: always read
                found.append(read_folder(path))
        elif path in by_path:
            found.append(by_path[path])

    maps, dialog, mods = {}, {}, {}
    holders = {}  # (map SID, side) -> IDs of the mods whose zip has that side's .bin
    for info in filter(None, found):
        mod_id = info["id"]
        mods.setdefault(mod_id, ModFiles(mod_id, info["source"]))
        for path in info["bins"]:
            sid, side = split_side(path)
            set_name = sid.rpartition("/")[0]
            if set_name:
                maps.setdefault(set_name, {}).setdefault(sid, set()).add(side)
                holders.setdefault((sid, side), []).append(mod_id)
        for k, v in info["dialog"].items():
            dialog.setdefault(k, v)
    return ModInfo(maps, dialog, mods_dir, mods, assign_owners(maps, holders, mods))


def assign_owners(maps, holders, mods):
    """Each chapter belongs to the mod whose zip holds its .bin (its A side, else its B/C side). If several
    zips hold the same file, the mod with more files in that level set wins."""
    in_set = {}  # (mod ID, level set) -> number of .bin files
    for (sid, _), ids in holders.items():
        for mod_id in ids:
            key = (mod_id, sid.rpartition("/")[0])
            in_set[key] = in_set.get(key, 0) + 1
    owner = {}
    for set_name, chapters in maps.items():
        for sid in chapters:
            ids = next(holders[(sid, s)] for s in "ABC" if (sid, s) in holders)
            owner[sid] = max(dict.fromkeys(ids), key=lambda m: in_set[(m, set_name)])
            mods[owner[sid]].chapters.add(sid)
    return owner


def load_mods(mods_dir, cache=None):
    """Scan the Mods folder, or return an empty ModInfo when there is none."""
    if mods_dir is None:
        return ModInfo()
    if not mods_dir.is_dir():
        print(f"Note: no Mods folder at {mods_dir}; skipping titles and map totals. Pass --mods <folder>.", file=sys.stderr)
        return ModInfo()
    return scan_mods(mods_dir, cache)
