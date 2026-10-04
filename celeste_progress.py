#!/usr/bin/env python3
"""
celeste_progress.py - per-level-set progress and notes from a Celeste save.

Celeste (with Everest) keeps progress for every level set / mod map in the save
slot, so this shows where you are on all of them without opening the game.

Usage:
    python celeste_progress.py                       # show progress
    python celeste_progress.py --note KEY "text"     # attach a note to a level set or a map
    python celeste_progress.py --note KEY ""         # remove that note
    python celeste_progress.py --markdown progress.md
    python celeste_progress.py --slot 1 | --saves <Saves folder> | --file <save file>
    python celeste_progress.py --mods [FOLDER]       # read titles and map totals from your Mods folder
    python celeste_progress.py --mods --set KEY      # every map of one level set (KEY: ID or title, or part)
    python celeste_progress.py --dump                # print raw XML structure (debugging)

KEY can be a level set name or a map name, exact or just a unique part of it
(e.g. --note DustValley "stopped at room 12").

Notes are stored next to this script in celeste_notes.json; override with --notes.

Note: a save only contains entries for maps you have opened at least once, so
for mods "Done/Maps" counts opened maps, not every map a collab contains.
Vanilla is shown out of its 11 chapters. With --mods, the Mods folder is read
(zip file lists and each mod's Dialog/English.txt only, nothing is loaded) to get
the real map count of each level set and the in-game titles of sets, maps and
checkpoints. The save itself only stores internal IDs.
"""
import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

TICKS_PER_SECOND = 10_000_000
HERE = Path(__file__).resolve().parent
NOT_LOADED = " [not loaded]"
VANILLA_CHAPTERS = 11  # Prologue, chapters 1-7, Epilogue, Core, Farewell


# ---------------------------------------------------------------- locating files

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


def find_save(args):
    if args.file:
        return Path(args.file)
    dirs = [Path(args.saves)] if args.saves else default_saves_dirs()
    for d in dirs:
        p = d / f"{args.slot}.celeste"
        if p.exists():
            return p
    sys.exit("Could not find the save file. Use --saves <folder> or --file <path>.")


# ---------------------------------------------------------------- mod data (titles, map totals)

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


def load_mods(args, save_path):
    if args.mods is None:
        return ModInfo()
    mods_dir = save_path.parent.parent / "Mods" if args.mods == "auto" else Path(args.mods)
    if not mods_dir.is_dir():
        print(f"Note: no Mods folder at {mods_dir}; skipping titles and map totals. Pass --mods <folder>.")
        return ModInfo()
    return scan_mods(mods_dir)


# ---------------------------------------------------------------- XML helpers

def local(tag):
    return tag.split("}", 1)[-1]


def child(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def text(el, name, default=""):
    """Value of `name` on `el`, as an XML attribute first, else as a child element's text."""
    attr = el.get(name)
    if attr is not None:
        return attr.strip()
    c = child(el, name)
    return (c.text or default).strip() if c is not None and c.text else default


def as_int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


def as_bool(s):
    return str(s).strip().lower() == "true"


def fmt_time(ticks):
    secs = ticks // TICKS_PER_SECOND
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def iter_local(root, name):
    return (e for e in root.iter() if local(e.tag) == name)


# ---------------------------------------------------------------- parsing the save

def parse_area(area_el):
    """Return a dict for one AreaStats element, merged over its modes (A/B/C)."""
    ident = text(area_el, "SID") or text(area_el, "ID_Safe") or text(area_el, "ID")
    info = {"id": ident, "completed": False, "touched": False, "deaths": 0,
            "ticks": 0, "berries": 0, "heart": False, "modes": [], "checkpoints": {}}
    modes = child(area_el, "Modes")
    mode_els = [m for m in modes if local(m.tag) == "AreaModeStats"] if modes is not None else []
    for i, m in enumerate(mode_els):
        ticks = as_int(text(m, "TimePlayed"))
        deaths = as_int(text(m, "Deaths"))
        done = as_bool(text(m, "Completed"))
        berries = as_int(text(m, "TotalStrawberries"))
        heart = as_bool(text(m, "HeartGem"))
        side = "ABC"[i] if i < 3 else str(i)
        cps_el = child(m, "Checkpoints")
        cps = [(c.text or "").strip() for c in cps_el if local(c.tag) == "string"] if cps_el is not None else []
        if cps:
            info["checkpoints"][side] = cps
        if done or ticks > 0 or deaths > 0 or cps:
            info["touched"] = True
            info["modes"].append(side)
        info["completed"] = info["completed"] or done
        info["deaths"] += deaths
        info["ticks"] += ticks
        info["berries"] += berries
        info["heart"] = info["heart"] or heart
    return info


def parse_save(path):
    root = ET.parse(path).getroot()
    last_area = ""
    la = next(iter_local(root, "LastArea_Safe"), None)
    if la is None:
        la = next(iter_local(root, "LastArea"), None)
    if la is not None:
        last_area = text(la, "SID") or (la.text or "").strip()

    def read_areas(areas_el, fallback_prefix):
        areas = []
        if areas_el is not None:
            for i, a in enumerate(x for x in areas_el if local(x.tag) == "AreaStats"):
                info = parse_area(a)
                if not info["id"]:
                    info["id"] = f"{fallback_prefix} #{i}"
                areas.append(info)
        return areas

    sets = []
    # Vanilla chapters live in the top-level <Areas> block.
    vanilla = read_areas(child(root, "Areas"), "chapter")
    if vanilla:
        sets.append({"name": "Celeste (vanilla)", "not_loaded": False, "areas": vanilla,
                     "total": VANILLA_CHAPTERS})
    # Mod level sets. Sets Everest did not load at the last save sit in the recycle bin.
    for block, not_loaded in (("LevelSets", False), ("LevelSetRecycleBin", True)):
        block_el = child(root, block)
        if block_el is None:
            continue
        for ls in (x for x in block_el if local(x.tag) == "LevelSetStats"):
            sets.append({"name": text(ls, "Name") or "(unnamed)", "not_loaded": not_loaded,
                         "areas": read_areas(child(ls, "Areas"), "map")})
    return sets, last_area, read_session(root, sets)


SIDES = {"Normal": "A", "BSide": "B", "CSide": "C"}


def read_session(root, sets):
    """The saved mid-map session (Save & Quit), or None. One per slot, for the last-played map."""
    cs = next(iter_local(root, "CurrentSession_Safe"), None)
    if cs is None:
        cs = next(iter_local(root, "CurrentSession"), None)
    area = child(cs, "Area") if cs is not None else None
    if cs is None or area is None or not cs.get("Level"):
        return None
    sid = text(area, "SID")
    side = SIDES.get(area.get("Mode", "Normal"), "A")
    cps = []
    for st in sets:
        for a in st["areas"]:
            if a["id"] == sid:
                cps = a["checkpoints"].get(side, [])
    return {"sid": sid, "side": side, "room": cs.get("Level"),
            "start_checkpoint": cs.get("StartCheckpoint") or "",
            "deaths": as_int(cs.get("Deaths")), "checkpoints": cps}


def summarize(sets, last_area, mods):
    rows = []
    for s in sets:
        touched = [a for a in s["areas"] if a["touched"]]
        if not touched:
            continue
        done = sum(1 for a in touched if a["completed"])
        in_prog = [a for a in touched if not a["completed"]]
        total = s.get("total") or mods.total(s["name"])
        if total:
            total = max(total, len(touched))
            status = "complete" if done >= total else ("in progress" if done else "started")
        elif done and not in_prog:
            status = "all opened done"
        elif done:
            status = "in progress"
        else:
            status = "started"
        # Latest checkpoint: from the unfinished map with checkpoints you've played longest.
        cands = [a for a in in_prog if a["checkpoints"]]
        latest, latest_title = "", ""
        if cands:
            best = max(cands, key=lambda a: a["ticks"])
            latest = best["checkpoints"][list(best["checkpoints"])[-1]][-1]
            latest_title = mods.checkpoint(best["id"], latest)
        rows.append({
            "latest_ckpt": latest_title or latest,
            "name": s["name"],
            "title": mods.title(s["name"]),
            "not_loaded": s["not_loaded"],
            "total": total,
            "opened": len(touched),
            "done": done,
            "status": status,
            "deaths": sum(a["deaths"] for a in touched),
            "ticks": sum(a["ticks"] for a in touched),
            "berries": sum(a["berries"] for a in touched),
            "completed_maps": [a["id"] for a in touched if a["completed"]],
            "unfinished": [a["id"] for a in in_prog],
            "checkpoints": {a["id"]: a["checkpoints"] for a in touched if a["checkpoints"]},
            "ckpt_count": sum(len(c) for a in in_prog for c in a["checkpoints"].values()),
            "is_last": bool(last_area) and any(a["id"] == last_area for a in s["areas"]),
        })
    rows.sort(key=lambda r: (-int(r["is_last"]), -r["ticks"]))
    return rows


def fmt_room(mods, sid, room):
    """'c-01' -> 'c-01 "Hypothermia"' when the mod names that checkpoint."""
    t = mods.checkpoint(sid, room)
    return f'{room} "{t}"' if t else room


def fmt_checkpoints(cps, mods, sid):
    """{'A': ['6', '9b']} -> 'A: 2 (6, 9b)'"""
    return "; ".join(f"{side}: {len(rooms)} ({', '.join(fmt_room(mods, sid, r) for r in rooms)})"
                     for side, rooms in cps.items())


def map_label(sid, mods):
    t = mods.title(sid)
    return f"{t} ({sid})" if t else sid


def fmt_session(sess, mods):
    sid, t = sess["sid"], mods.title(sess["sid"])
    out = f"Resume: {t} ({sid}, {sess['side']}-side)" if t else f"Resume: {sid} ({sess['side']}-side)"
    out += f", room {sess['room']}"
    if sess["start_checkpoint"]:
        out += f", started from checkpoint room {sess['start_checkpoint']}"
    out += f", {sess['deaths']} death(s) this session"
    if sess["checkpoints"]:
        out += (f"; {len(sess['checkpoints'])} checkpoint(s) reached "
                f"({', '.join(fmt_room(mods, sid, r) for r in sess['checkpoints'])})")
    return out


def ckpt_note(r, session):
    """Current room for the last-played set, else its latest checkpoint (last one listed in the save)."""
    if r["is_last"] and session:
        return f" (room {session['room']})"
    return f" (ckpt {r['latest_ckpt']})" if r["latest_ckpt"] else ""


def label(r):
    base = f"{r['title']} ({r['name']})" if r["title"] else r["name"]
    return base + (NOT_LOADED if r["not_loaded"] else "")


# ---------------------------------------------------------------- JSON files

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        sys.exit(f"{path} is not valid JSON ({e}). Fix or delete it and run again.")


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- notes

def resolve_note_key(key, sets, mods):
    """Match KEY to a level set or map ID (or its in-game title): exact ID, else a unique substring."""
    names = []
    for s in sets:
        names.append(s["name"])
        names.extend(a["id"] for a in s["areas"] if a["id"])
    names = list(dict.fromkeys(names))
    if key in names:
        return key
    low = key.lower()
    hits = [n for n in names if low in n.lower() or (mods.title(n) and low in mods.title(n).lower())]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        sys.exit(f"'{key}' matches several entries, be more specific:\n  "
                 + "\n  ".join(map_label(n, mods) for n in hits[:12]))
    print(f"Note: '{key}' wasn't found in the save; storing the note under that exact key.")
    return key


def set_note(args, sets, mods):
    notes = load_json(args.notes, {})
    key, note = args.note
    key = resolve_note_key(key, sets, mods)
    if note.strip():
        notes[key] = note.strip()
        print(f"Saved note for {key}: {note.strip()}")
    elif key in notes:
        del notes[key]
        print(f"Removed note for {key}")
    else:
        print(f"No note stored for {key}")
    save_json(args.notes, notes)


# ---------------------------------------------------------------- rendering

def render_text(rows, last_area, notes, session=None, mods=None):
    mods = mods or ModInfo()
    out = []
    labels = [label(r) for r in rows]
    w = max([len(x) for x in labels] + [9])
    out.append(f"{'Level set':<{w}}  {'Done/Maps':<11}  {'Status':<15}  {'Deaths':>6}  {'Time':<9}  {'Berries':>7}  Ckpts")
    out.append("-" * (w + 66))
    for r, lab in zip(rows, labels):
        mark = " *" if r["is_last"] else ""
        room = ckpt_note(r, session)
        cell = f"{r['done']}/{r['total'] or r['opened']}"
        out.append(f"{lab:<{w}}  {cell:<11}  {r['status']:<15}  {r['deaths']:>6}  "
                   f"{fmt_time(r['ticks']):<9}  {r['berries']:>7}  {r['ckpt_count']:>5}{room}{mark}")
        if r["name"] in notes:
            out.append(f"{'':<{w}}    note: {notes[r['name']]}")
    out.append("")
    if last_area:
        out.append(f"* = contains your last-played map ({last_area})")
    if session:
        out.append(fmt_session(session, mods))
    out.append("Ckpts = checkpoints reached in unfinished maps (finished maps are listed separately). (room X) = your saved room, only for the last-played set; (ckpt X) = latest checkpoint listed. They are room IDs; the start of a map isn't listed. A save doesn't record how many a map has.")
    if mods.maps:
        out.append("Maps: totals come from your Mods folder. A set with no matching mod there counts "
                   "only the maps you've opened, and shows 'all opened done' when those are finished.")
    else:
        out.append("Maps: vanilla counts all 11 chapters; for mods it counts only maps you've opened "
                   "(a save doesn't record how many maps a mod has). Use --mods for real totals and titles.")
    if any(r["not_loaded"] for r in rows):
        out.append("[not loaded] = Everest didn't load that mod the last time the game saved; "
                   "its progress is kept aside.")
    shown = {r["name"] for r in rows}
    unfinished = [r for r in rows if r["unfinished"]]
    if unfinished:
        out.append("\nOpened but not completed:")
        for r in unfinished:
            out.append(f"  {label(r)}")
            for a in r["unfinished"]:
                shown.add(a)
                note = f"   <- {notes[a]}" if a in notes else ""
                cps = (f"  [checkpoints {fmt_checkpoints(r['checkpoints'][a], mods, a)}]"
                       if a in r["checkpoints"] else "")
                out.append(f"    - {map_label(a, mods)}{cps}{note}")
    finished = [(r, a) for r in rows for a in r["completed_maps"] if a in r["checkpoints"]]
    if finished:
        out.append("\nCompleted maps, checkpoints reached:")
        for r, a in finished:
            out.append(f"  {map_label(a, mods)}  [{fmt_checkpoints(r['checkpoints'][a], mods, a)}]")
    rest = {k: v for k, v in notes.items() if k not in shown}
    if rest:
        out.append("\nOther notes:")
        known = {a for r in rows for a in r["completed_maps"] + r["unfinished"]}
        for k, v in rest.items():
            flag = "" if k in known else "  (not in save)"
            out.append(f"  {k}: {v}{flag}")
    return "\n".join(out)


def render_markdown(rows, last_area, notes, session=None, mods=None):
    mods = mods or ModInfo()
    out = ["| Level set | Done/Maps | Status | Deaths | Time | Berries | Checkpoints | Unfinished maps | Notes |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        name = label(r) + (" (last played)" if r["is_last"] else "")
        room = ckpt_note(r, session)
        maps = ", ".join(f"{map_label(a, mods)} [{fmt_checkpoints(r['checkpoints'][a], mods, a)}]"
                         if a in r["checkpoints"] else map_label(a, mods) for a in r["unfinished"])
        rn = "; ".join(f"{k}: {v}" for k, v in notes.items()
                       if k == r["name"] or k in r["unfinished"] or k in r["completed_maps"])
        out.append(f"| {name} | {r['done']}/{r['total'] or r['opened']} | {r['status']} | {r['deaths']} | "
                   f"{fmt_time(r['ticks'])} | {r['berries']} | {r['ckpt_count']}{room} | {maps} | {rn} |")
    return "\n".join(out) + "\n"


def find_set(key, sets, mods):
    """The one level set KEY names: exact ID or title, else a unique case-insensitive substring."""
    cands = [s for s in sets if s["areas"] or mods.total(s["name"])]
    low = key.lower()
    hits = [s for s in cands if key in (s["name"], mods.title(s["name"]))]
    hits = hits or [s for s in cands if low in s["name"].lower() or low in mods.title(s["name"]).lower()]
    if not hits:
        sys.exit(f"No level set matches '{key}'.")
    if len(hits) > 1:
        sys.exit(f"'{key}' matches several level sets, be more specific:\n  "
                 + "\n  ".join(label({"title": mods.title(h["name"]), "name": h["name"],
                                       "not_loaded": h["not_loaded"]}) for h in hits[:15]))
    return hits[0]


def render_set(s, last_area, notes, mods):
    """Every map of one level set: the ones in the save plus, with --mods, the ones never opened."""
    by_id = {a["id"]: a for a in s["areas"]}
    known = mods.maps.get(s["name"], {})
    order = list(by_id) + sorted(known.keys() - by_id.keys())
    maps = []
    for i, sid in enumerate(order):
        a = by_id.get(sid)
        if a and a["completed"]:
            status, rank = "done", 1
        elif a and a["touched"]:
            status, rank = "in progress", 0
        else:
            status, rank = "not opened", 2
        maps.append((rank, i, sid, status, a))
    maps.sort(key=lambda m: m[:2])  # in progress, then done, then not opened; stable inside each group

    counts = {st: sum(1 for m in maps if m[3] == st) for st in ("done", "in progress", "not opened")}
    head = label({"title": mods.title(s["name"]), "name": s["name"], "not_loaded": s["not_loaded"]})
    out = [head,
           f"{counts['done']}/{len(maps)} done, {counts['in progress']} in progress, "
           f"{counts['not opened']} not opened", ""]
    labels = []
    for _, _, sid, _, _ in maps:
        t, short = mods.title(sid), sid.rpartition("/")[2]
        labels.append(f"{t} ({short})" if t else short)
    w = max([len(x) for x in labels] + [3])
    if known:  # which sides each map has, from its .bin files
        labels = [f"{lab:<{w}}  {' '.join(mods.sides(m[2])):<5}" for lab, m in zip(labels, maps)]
        w = max(len(x) for x in labels)
        out.append(f"{'Map':<{w - 7}}  Sides  {'Status':<11}  {'Deaths':>6}  {'Time':<9}  {'Berries':>7}  Checkpoints")
    else:
        out.append(f"{'Map':<{w}}  {'Status':<11}  {'Deaths':>6}  {'Time':<9}  {'Berries':>7}  Checkpoints")
    out.append("-" * (w + 52))
    for (_, _, sid, status, a), lab in zip(maps, labels):
        star = " *" if sid == last_area else ""
        if a and a["touched"]:
            cps = fmt_checkpoints(a["checkpoints"], mods, sid) if a["checkpoints"] else ""
            cells = f"{a['deaths']:>6}  {fmt_time(a['ticks']):<9}  {a['berries']:>7}  {cps}"
        else:
            cells = f"{'-':>6}  {'-':<9}  {'-':>7}"
        note = f"   <- {notes[sid]}" if sid in notes else ""
        out.append(f"{lab:<{w}}  {status:<11}  {cells}{star}{note}".rstrip())
    out.append("")
    if last_area in by_id:
        out.append("* = your last-played map")
    if not known:
        out.append("Only maps you've opened are listed: " + ("no mod for this set was found in the Mods folder."
                   if mods.maps else "add --mods to also list the ones you haven't."))
    return "\n".join(out)


def dump(path, depth=7, per_tag=2):
    """Print the XML structure with attributes, showing at most `per_tag` siblings of each tag."""
    root = ET.parse(path).getroot()

    def walk(el, d):
        if d > depth:
            return
        t = (el.text or "").strip()
        attrs = "".join(f" [{k}={v[:40]}]" for k, v in el.attrib.items())
        print("  " * d + local(el.tag) + attrs + (f" = {t[:40]}" if t else ""))
        counts = {}
        for c in el:
            tag = local(c.tag)
            counts[tag] = counts.get(tag, 0) + 1
            if counts[tag] <= per_tag:
                walk(c, d + 1)
        for tag, n in counts.items():
            if n > per_tag:
                print("  " * (d + 1) + f"... (+{n - per_tag} more <{tag}>)")

    walk(root, 0)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Per-level-set progress and notes from a Celeste save.")
    ap.add_argument("--slot", type=int, default=0)
    ap.add_argument("--saves", help="path to the Saves folder")
    ap.add_argument("--file", help="path to a specific .celeste save file")
    ap.add_argument("--markdown", help="also write a markdown table to this file")
    ap.add_argument("--dump", action="store_true", help="print the XML structure and exit")
    ap.add_argument("--note", nargs=2, metavar=("KEY", "TEXT"),
                    help="set a note on a level set or map (empty TEXT removes it)")
    ap.add_argument("--set", metavar="KEY", help="list every map of one level set (ID or title, or part of it)")
    ap.add_argument("--mods", nargs="?", const="auto", metavar="FOLDER",
                    help="read titles and map totals from the Mods folder (default: next to Saves)")
    ap.add_argument("--notes", default=str(HERE / "celeste_notes.json"), help="notes file")
    args = ap.parse_args()

    path = find_save(args)
    if args.dump:
        dump(path)
        return

    sets, last_area, session = parse_save(path)
    mods = load_mods(args, path)
    if args.note:
        set_note(args, sets, mods)
        return

    if args.set:
        print(render_set(find_set(args.set, sets, mods), last_area, load_json(args.notes, {}), mods))
        return

    rows = summarize(sets, last_area, mods)
    if not rows:
        print(f"No level-set progress found in {path}. Try --dump to inspect the file structure.")
        return

    notes = load_json(args.notes, {})

    print(f"Save: {path}")
    if mods.source:
        print(f"Mods: {mods.source} ({mods.summary()})")
    print()
    print(render_text(rows, last_area, notes, session, mods))

    if args.markdown:
        Path(args.markdown).write_text(render_markdown(rows, last_area, notes, session, mods), encoding="utf-8")
        print(f"\nMarkdown written to {args.markdown}")


if __name__ == "__main__":
    main()