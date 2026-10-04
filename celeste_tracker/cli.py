"""Command line: argument parsing and text / markdown rendering of the model."""
import argparse
import sys
from pathlib import Path

from .core import load_slots
from .export import to_json
from .mods import load_mods
from .paths import (config_path, find_save, find_saves_dir, list_slots, load_config, mods_dir_for,
                    write_config)
from .save import dump
from .store import DEFAULT_NOTES, load_json, save_json

TICKS_PER_SECOND = 10_000_000
NOT_LOADED = " [not loaded]"
MOD_WIDTH = 24


def fmt_time(ticks):
    secs = ticks // TICKS_PER_SECOND
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_cp(cp):
    """Checkpoint -> 'c-01 "Hypothermia"' when the mod names it, else the room ID."""
    return f'{cp.room} "{cp.title}"' if cp.title else cp.room


def fmt_cps(cps):
    return f"{len(cps)} ({', '.join(fmt_cp(c) for c in cps)})" if cps else ""


def short(text, width):
    return text if len(text) <= width else text[:width - 1] + "…"


def map_label(m):
    return f"{m.title} ({m.sid})" if m.title else m.sid


def set_label(ls):
    base = f"{ls.title} ({ls.name})" if ls.title else ls.name
    return base + ("" if ls.loaded else NOT_LOADED)


def sides_cell(ls):
    return f"{ls.sides_done}/{ls.sides_total}" + ("" if ls.sides_known else "?")


def maps_cell(ls):
    return f"{ls.maps_done}/{ls.maps_total}" + ("" if ls.sides_known else "?")


def fmt_session(slot):
    sess = slot.session
    name = f"{sess.title} ({sess.sid}" if sess.title else f"{sess.sid} ("
    out = f"Resume: {name}{', ' if sess.title else ''}{sess.side}-side), room {sess.room}"
    if sess.start_checkpoint:
        out += f", started from checkpoint room {sess.start_checkpoint}"
    out += f", {sess.deaths} death(s) this session"
    if sess.checkpoints:
        out += f"; {len(sess.checkpoints)} checkpoint(s) reached ({', '.join(fmt_cp(c) for c in sess.checkpoints)})"
    return out


def ckpt_note(ls, slot):
    """Current room for the last-played set, else its latest checkpoint."""
    if ls.last_played and slot.session:
        return f" (room {slot.session.room})"
    lc = ls.latest_checkpoint
    return f" (ckpt {lc['title'] or lc['room']})" if lc else ""


def side_summary(m):
    """'done: A B; C: in progress, checkpoints 2 (b-01, c-01)' for a map that isn't completed."""
    done = [s.side for s in m.sides.values() if s.status == "completed"]
    new = [s.side for s in m.sides.values() if s.status == "not opened"]
    parts = [f"done: {' '.join(done)}"] if done else []
    for s in m.sides.values():
        if s.status not in ("completed", "not opened"):
            cps = f", checkpoints {fmt_cps(s.checkpoints)}" if s.checkpoints else ""
            parts.append(f"{s.side}: {s.status}{cps}")
    if new:
        parts.append(f"not opened: {' '.join(new)}")
    return "; ".join(parts)


# ---------------------------------------------------------------- overview

def overview_rows(slots):
    return [(slot, ls) for slot in slots for ls in slot.sets if ls.status != "not started"]


def render_text(slots, notes, mods):
    multi = len(slots) > 1
    rows = overview_rows(slots)
    labels = [set_label(ls) for _, ls in rows]
    w = max([len(x) for x in labels] + [9])
    show_mod = any(ls.mod_name for _, ls in rows)
    mw = min(max([len(ls.mod_name) for _, ls in rows] + [3]), MOD_WIDTH)
    mod_head = f"  {'Mod':<{mw}}" if show_mod else ""
    slot_head = "Slot  " if multi else ""
    out = [f"{slot_head}{'Level set':<{w}}{mod_head}  {'Sides':<7}  {'Maps':<7}  {'Status':<15}  "
           f"{'Deaths':>6}  {'Time':<9}  {'Berries':>7}  Ckpts"]
    out.append("-" * (len(slot_head) + w + len(mod_head) + 75))
    for (slot, ls), lab in zip(rows, labels):
        mark = " *" if ls.last_played and not multi else ""
        slot_cell = f"{slot.number if slot.number is not None else '-':>4}  " if multi else ""
        mod_cell = f"  {short(ls.mod_name, mw):<{mw}}" if show_mod else ""
        out.append(f"{slot_cell}{lab:<{w}}{mod_cell}  {sides_cell(ls):<7}  {maps_cell(ls):<7}  "
                   f"{ls.status:<15}  {ls.deaths:>6}  {fmt_time(ls.ticks):<9}  {ls.berries:>7}  "
                   f"{ls.open_checkpoints:>5}{ckpt_note(ls, slot)}{mark}")
        if ls.name in notes:
            out.append(f"{'':<{len(slot_cell) + w}}    note: {notes[ls.name]}")
    out.append("")
    for slot in slots:
        prefix = f"Slot {slot.number}: " if multi else ""
        if slot.last_played_sid and not multi:
            out.append(f"* = contains your last-played map ({slot.last_played_sid})")
        if slot.session:
            out.append(prefix + fmt_session(slot))
    out.append("Sides = sides completed (cleared + heart, or cleared when the side has no heart) out of all sides; "
               "Maps = maps with every side completed. A map's B and C sides count once each.")
    if any(ls.status == "hearts missing" or ls.sides_no_heart for _, ls in rows):
        out.append("hearts missing = every side is cleared but some hearts aren't collected. For mods the tool can't "
                   "yet tell whether a side has a heart at all (lobbies often don't), so those sides aren't counted as done.")
    if any(not ls.sides_known for _, ls in rows):
        out.append("? = total unknown: no mod for that set was found" + (" in the Mods folder" if mods.maps else
                   " (use --mods)") + ", so only what you've opened is counted.")
    out.append("Ckpts = checkpoints reached in sides not yet completed. (room X) = your saved room, only for the "
               "last-played set; (ckpt X) = latest checkpoint listed. A save doesn't record how many a map has.")
    if any(not ls.loaded for _, ls in rows):
        out.append("[not loaded] = Everest didn't load that mod the last time the game saved; its progress is kept aside.")
    if multi:
        out.append("Use --slot N for the unfinished maps of one slot.")
        return "\n".join(out)

    shown = {ls.name for _, ls in rows}
    unfinished = [(ls, [m for m in ls.maps if m.status == "in progress"]) for _, ls in rows]
    unfinished = [(ls, ms) for ls, ms in unfinished if ms]
    if unfinished:
        out.append("\nOpened but not completed:")
        for ls, ms in unfinished:
            out.append(f"  {set_label(ls)}")
            for m in ms:
                shown.add(m.sid)
                note = f"   <- {notes[m.sid]}" if m.sid in notes else ""
                out.append(f"    - {map_label(m)}  {side_summary(m)}{note}")
    rest = {k: v for k, v in notes.items() if k not in shown}
    if rest:
        out.append("\nOther notes:")
        known = {m.sid for _, ls in rows for m in ls.maps}
        for k, v in rest.items():
            out.append(f"  {k}: {v}" + ("" if k in known else "  (not in save)"))
    return "\n".join(out)


def render_markdown(slots, notes):
    multi = len(slots) > 1
    head = ["Slot"] * multi + ["Level set", "Mod", "Sides", "Maps", "Status", "Deaths", "Time", "Berries",
                               "Checkpoints", "Unfinished maps", "Notes"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for slot, ls in overview_rows(slots):
        name = set_label(ls) + (" (last played)" if ls.last_played else "")
        maps = ", ".join(f"{map_label(m)} [{side_summary(m)}]" for m in ls.maps if m.status == "in progress")
        sids = {m.sid for m in ls.maps}
        rn = "; ".join(f"{k}: {v}" for k, v in notes.items() if k == ls.name or k in sids)
        cells = [str(slot.number)] * multi + [
            name, ls.mod_name, sides_cell(ls), maps_cell(ls), ls.status, str(ls.deaths), fmt_time(ls.ticks),
            str(ls.berries), f"{ls.open_checkpoints}{ckpt_note(ls, slot)}", maps, rn]
        out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- one level set

def find_set(key, slot):
    """The one level set KEY names: exact ID, title or mod name, else a unique case-insensitive substring."""
    cands = [ls for ls in slot.sets if ls.maps]
    low = key.lower()
    hits = [ls for ls in cands if key in (ls.name, ls.title, ls.mod_name)]
    hits = hits or [ls for ls in cands if any(low in x.lower() for x in (ls.name, ls.title, ls.mod_name))]
    if not hits:
        sys.exit(f"No level set matches '{key}'.")
    if len(hits) > 1:
        sys.exit(f"'{key}' matches several level sets, be more specific:\n  "
                 + "\n  ".join(set_label(h) for h in hits[:15]))
    return hits[0]


def render_set(ls, slot, notes):
    """Every map of one level set and each of its sides, including the ones never opened."""
    rank = {"in progress": 0, "completed": 1, "not opened": 2}
    maps = sorted(ls.maps, key=lambda m: rank[m.status])  # stable inside each group
    n_prog = sum(m.status == "in progress" for m in maps)
    n_new = sum(m.status == "not opened" for m in maps)
    mod = f"  (mod: {ls.mod_name})" if ls.mod_name and ls.mod_name not in (ls.title, ls.name) else ""
    out = [set_label(ls) + mod,
           f"Sides {sides_cell(ls)} done, maps {maps_cell(ls)} done ({n_prog} in progress, {n_new} not opened)"
           + (f", {ls.sides_no_heart} side(s) cleared without the heart" if ls.sides_no_heart else ""), ""]
    labels = [(m.title + (f" ({m.sid.rpartition('/')[2]})" if not ls.vanilla else "")) if m.title
              else m.sid.rpartition("/")[2] for m in maps]
    w = max([len(x) for x in labels] + [3])
    out.append(f"{'Map':<{w}}  Side  {'Status':<17}  {'Deaths':>6}  {'Time':<9}  {'Berries':>7}  Checkpoints")
    out.append("-" * (w + 70))
    for m, lab in zip(maps, labels):
        star = " *" if m.sid == slot.last_played_sid else ""
        note = f"   <- {notes[m.sid]}" if m.sid in notes else ""
        if not m.sides:
            out.append(f"{lab:<{w}}  {'-':<4}  {'not opened':<17}{star}{note}")
            continue
        for i, s in enumerate(m.sides.values()):
            if s.opened:
                cells = f"{s.deaths:>6}  {fmt_time(s.ticks):<9}  {s.berries:>7}  {fmt_cps(s.checkpoints)}"
            else:
                cells = f"{'-':>6}  {'-':<9}  {'-':>7}"
            first = i == 0
            out.append(f"{lab if first else '':<{w}}  {s.side:<4}  {s.status:<17}  {cells}"
                       f"{star if first else ''}{note if first else ''}".rstrip())
    out.append("")
    if ls.find_map(slot.last_played_sid):
        out.append("* = your last-played map")
    if ls.sides_no_heart:
        out.append("cleared, no heart = cleared without collecting the heart. For mods the tool can't yet tell "
                   "whether that side has a heart at all.")
    if not ls.sides_known:
        out.append("Only maps and sides you've opened are listed: no mod for this set was found"
                   + (" in the Mods folder." if ls.title or ls.mod_name else ". Use --mods to read the Mods folder."))
    return "\n".join(out)


# ---------------------------------------------------------------- notes

def resolve_note_key(key, slots):
    """Match KEY to a level set or map ID (or its in-game title): exact ID, else a unique substring."""
    titles = {}
    for slot in slots:
        for ls in slot.sets:
            titles.setdefault(ls.name, ls.title)
            for m in ls.maps:
                titles.setdefault(m.sid, m.title)
    if key in titles:
        return key
    low = key.lower()
    hits = [n for n, t in titles.items() if low in n.lower() or (t and low in t.lower())]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        sys.exit(f"'{key}' matches several entries, be more specific:\n  "
                 + "\n  ".join(f"{titles[n]} ({n})" if titles[n] else n for n in hits[:12]))
    print(f"Note: '{key}' wasn't found in the save; storing the note under that exact key.")
    return key


def set_note(notes_path, key, note, slots):
    notes = load_json(notes_path, {})
    key = resolve_note_key(key, slots)
    if note.strip():
        notes[key] = note.strip()
        print(f"Saved note for {key}: {note.strip()}")
    elif key in notes:
        del notes[key]
        print(f"Removed note for {key}")
    else:
        print(f"No note stored for {key}")
    save_json(notes_path, notes)


# ---------------------------------------------------------------- main

def parse_args(argv):
    ap = argparse.ArgumentParser(description="Celeste mod progress from save files, without loading the mods.")
    ap.add_argument("--slot", type=int, default=0, help="save slot number (default 0)")
    ap.add_argument("--all", action="store_true", help="every save slot in the Saves folder")
    ap.add_argument("--saves", help="path to the Saves folder")
    ap.add_argument("--file", help="path to a specific .celeste save file")
    ap.add_argument("--mods", nargs="?", const="auto", metavar="FOLDER",
                    help="read titles, map and side totals from the Mods folder (default: next to Saves)")
    ap.add_argument("--no-mods", action="store_true", help="don't read the Mods folder, even if the config says to")
    ap.add_argument("--set", metavar="KEY", help="every map and side of one level set (ID, title, mod name or part)")
    ap.add_argument("--note", nargs=2, metavar=("KEY", "TEXT"),
                    help="set a note on a level set or map (empty TEXT removes it)")
    ap.add_argument("--notes", default=str(DEFAULT_NOTES), help="notes file")
    ap.add_argument("--markdown", metavar="FILE", help="also write a markdown table to this file")
    ap.add_argument("--json", metavar="FILE", help="write everything parsed as JSON to FILE ('-' for stdout)")
    ap.add_argument("--dump", action="store_true", help="print the XML structure and exit")
    ap.add_argument("--config", help=f"config file (default: {config_path()})")
    ap.add_argument("--save-config", action="store_true",
                    help="store the given --saves and --mods in the config file, so later runs don't need them")
    return ap.parse_args(argv)


def slot_number(path):
    return int(path.stem) if path.stem.isdigit() else None


def main(argv=None):
    args = parse_args(argv)
    cfg_file = Path(args.config) if args.config else config_path()
    cfg = load_config(cfg_file)
    saves = args.saves or cfg.get("saves")
    mods_arg = None if args.no_mods else (args.mods or cfg.get("mods"))

    if args.save_config:
        values = {**cfg, "saves": str(Path(args.saves).resolve()) if args.saves else cfg.get("saves"),
                  "mods": (args.mods if args.mods in (None, "auto") else str(Path(args.mods).resolve()))
                  or cfg.get("mods")}
        write_config(cfg_file, values)
        print(f"Config written to {cfg_file}:")
        print(cfg_file.read_text(encoding="utf-8").rstrip())
        return

    if args.all:
        if args.file or args.set or args.dump:
            sys.exit("--all can't be combined with --file, --set or --dump.")
        saves_dir = find_saves_dir(saves)
        if not saves_dir or not saves_dir.is_dir():
            sys.exit("Could not find the Saves folder. Use --saves <folder>.")
        slot_paths = list_slots(saves_dir)
        if not slot_paths:
            sys.exit(f"No save slots (N.celeste) in {saves_dir}.")
    else:
        path = find_save(args.file, saves, args.slot)
        slot_paths = [(slot_number(path), path)]
    if args.dump:
        dump(slot_paths[0][1])
        return

    mods = load_mods(mods_dir_for(slot_paths[0][1], mods_arg) if mods_arg else None)
    slots = load_slots(slot_paths, mods)

    if args.note:
        key, text = args.note
        set_note(args.notes, key, text, slots)
        return
    if args.json == "-":
        print(to_json(slots, mods))
        return
    notes = load_json(args.notes, {})
    if args.set:
        print(render_set(find_set(args.set, slots[0]), slots[0], notes))
        return
    if not overview_rows(slots):
        print(f"No level-set progress found in {slot_paths[0][1]}. Try --dump to inspect the file structure.")
        return

    if args.all:
        print(f"Saves: {slot_paths[0][1].parent} ({len(slots)} slots)")
    else:
        print(f"Save: {slot_paths[0][1]}")
    if mods.source:
        print(f"Mods: {mods.source} ({mods.summary()})")
    print()
    print(render_text(slots, notes, mods))

    if args.markdown:
        Path(args.markdown).write_text(render_markdown(slots, notes), encoding="utf-8")
        print(f"\nMarkdown written to {args.markdown}")
    if args.json:
        Path(args.json).write_text(to_json(slots, mods), encoding="utf-8")
        print(f"\nJSON written to {args.json}")
