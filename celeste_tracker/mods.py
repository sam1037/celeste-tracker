"""What the Mods folder knows that the save doesn't: map lists, sides and in-game titles.

Only zip file lists and each mod's Dialog/English.txt are read; nothing is loaded.
"""
import re
import zipfile

from .paths import mods_dir_for


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


def split_side(path):
    """'Set/Map-B' -> ('Set/Map', 'B'). Everest loads <map>-B.bin and <map>-C.bin as that map's B and C sides;
    any other name (including '-D') is a map of its own, A side."""
    m = re.fullmatch(r"(.+)-([BC])", path)
    return (m[1], m[2]) if m else (path, "A")


class ModInfo:
    """What the Mods folder knows that the save doesn't. Empty (all lookups blank) without --mods."""

    def __init__(self, maps=None, dialog=None, source=None):
        self.maps = maps or {}      # level set name -> {map SID: set of sides it has, e.g. {'A', 'B'}}
        self.dialog = dialog or {}  # lowercase dialog key -> text
        self.source = source

    def total(self, set_name):
        return len(self.maps.get(set_name, ()))

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
    maps, dialog = {}, {}

    def absorb(names, read):
        sids = [n[5:-4] for n in names if n.startswith("Maps/") and n.endswith(".bin")]
        if not sids:
            return
        for path in sids:
            sid, side = split_side(path)
            set_name = sid.rpartition("/")[0]
            if set_name:
                maps.setdefault(set_name, {}).setdefault(sid, set()).add(side)
        for n in names:
            if n.lower() == "dialog/english.txt":
                for k, v in parse_dialog(read(n)).items():
                    dialog.setdefault(k, v)

    for entry in sorted(mods_dir.iterdir()):
        try:
            if entry.is_dir():
                if (entry / "Maps").is_dir():
                    files = {p.relative_to(entry).as_posix(): p for p in (entry / "Maps").rglob("*.bin")}
                    d = entry / "Dialog" / "English.txt"
                    if d.is_file():
                        files["Dialog/English.txt"] = d
                    absorb(files, lambda n: files[n].read_bytes())
            elif entry.suffix.lower() == ".zip":
                with zipfile.ZipFile(entry) as z:
                    orig = {n.replace("\\", "/"): n for n in z.namelist()}
                    absorb(orig, lambda n: z.read(orig[n]))
        except (OSError, zipfile.BadZipFile):
            continue
    return ModInfo(maps, dialog, mods_dir)


def load_mods(mods_arg, save_path):
    if mods_arg is None:
        return ModInfo()
    mods_dir = mods_dir_for(save_path, mods_arg)
    if not mods_dir.is_dir():
        print(f"Note: no Mods folder at {mods_dir}; skipping titles and map totals. Pass --mods <folder>.")
        return ModInfo()
    return scan_mods(mods_dir)
