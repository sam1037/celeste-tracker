"""What the Mods folder knows that the save doesn't: map lists, sides and in-game titles.

Only zip file lists and each mod's Dialog/English.txt are read; nothing is loaded.
"""
import re
import sys
import zipfile
from dataclasses import dataclass, field


def dkey(ident):
    """Dialog key for an ID: Everest swaps '/', ' ' and '-' for '_' (compared case-insensitively)."""
    return re.sub(r"[/ \-]", "_", ident).lower()


def parse_dialog(raw):
    """`key= value` lines of a Dialog/English.txt as {lowercase key: value}."""
    out = {}
    for line in raw.decode("utf-8-sig", "replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out.setdefault(k.strip().lower(), v.strip())
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


def scan_mods(mods_dir):
    """Read map lists and English dialog from every mod (zip or unzipped folder) that has maps."""
    maps, dialog, mods = {}, {}, {}
    holders = {}  # (map SID, side) -> IDs of the mods whose zip has that side's .bin

    def absorb(names, read, source):
        sids = [n[5:-4] for n in names if n.startswith("Maps/") and n.endswith(".bin")]
        if not sids:
            return
        mod_id = next((mod_name(read(n)) for n in names if n.lower() in ("everest.yaml", "everest.yml")), "") or source
        mods.setdefault(mod_id, ModFiles(mod_id, source))
        for path in sids:
            sid, side = split_side(path)
            set_name = sid.rpartition("/")[0]
            if set_name:
                maps.setdefault(set_name, {}).setdefault(sid, set()).add(side)
                holders.setdefault((sid, side), []).append(mod_id)
        for n in names:
            if n.lower() == "dialog/english.txt":
                for k, v in parse_dialog(read(n)).items():
                    dialog.setdefault(k, v)

    for entry in sorted(mods_dir.iterdir()):
        try:
            if entry.is_dir():
                if (entry / "Maps").is_dir():
                    files = {p.relative_to(entry).as_posix(): p for p in (entry / "Maps").rglob("*.bin")}
                    for extra in ("Dialog/English.txt", "everest.yaml", "everest.yml"):
                        if (entry / extra).is_file():
                            files[extra] = entry / extra
                    absorb(files, lambda n: files[n].read_bytes(), entry.name)
            elif entry.suffix.lower() == ".zip":
                with zipfile.ZipFile(entry) as z:
                    orig = {n.replace("\\", "/"): n for n in z.namelist()}
                    absorb(orig, lambda n: z.read(orig[n]), entry.stem)
        except (OSError, zipfile.BadZipFile):
            continue
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


def load_mods(mods_dir):
    """Scan the Mods folder, or return an empty ModInfo when there is none."""
    if mods_dir is None:
        return ModInfo()
    if not mods_dir.is_dir():
        print(f"Note: no Mods folder at {mods_dir}; skipping titles and map totals. Pass --mods <folder>.", file=sys.stderr)
        return ModInfo()
    return scan_mods(mods_dir)
