"""Command line: argument parsing and text / markdown rendering of the model (doc/DESIGN.md, "Showing the tree")."""
import argparse
import sys
from pathlib import Path

from .core import load_library
from .export import to_json
from .model import View
from .moddb import load_titles
from .mods import load_mods
from .paths import (config_path, find_save, find_saves_dir, list_slots, load_config, mods_dir_for,
                    write_config)
from .rules import ALL
from .save import dump
from .store import DIFFICULTIES, Store, clean_tag

TICKS_PER_SECOND = 10_000_000
NOT_LOADED = " [not loaded]"
SLOTS_WIDTH = 14
RANK = {"in progress": 0, "completed": 1, "not opened": 2}


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


def chapter_label(ch):
    return f"{ch.title} ({ch.sid})" if ch.title else ch.sid


def set_label(ls):
    """Under its mod, a level set without a title only needs the last part of its ID ('0-Gyms')."""
    return ls.title or ls.name.rpartition("/")[2] or ls.name


def mod_label(mod, v):
    return mod.name + ("" if v.loaded else NOT_LOADED)


def known(mod):
    return mod.found or mod.vanilla


def sides_cell(v, mod):
    return f"{v.sides_done}/{v.sides_total}" + ("" if known(mod) else "?")


def maps_cell(v, mod):
    return f"{v.maps_done}/{v.maps_total}" + ("" if known(mod) else "?")


def slots_cell(v):
    """The slot shown and how many others the mod was played in: '8 (+5)'."""
    if not v.slot:
        return ""
    others = len(v.slots) - 1
    return short(f"{v.slot}" + (f" (+{others})" if others > 0 else ""), SLOTS_WIDTH)


def also_played(mod, key):
    """'Shown: slot 8, the furthest; also played in slot 1 (2/3), slot 31 (0/3)' for the all-slots view."""
    v = mod.progress.get(key)
    if key != ALL or not v or not v.slot:
        return ""
    others = [k for k in v.slots if k != v.slot]
    out = f"Shown: slot {v.slot}, the furthest"
    if others:
        out += "; also played in " + ", ".join(
            f"slot {k} ({mod.progress[k].sides_done}/{mod.progress[k].sides_total})" for k in others)
    return out


def view_of(node, key):
    return node.progress.get(key) or View(status="not started")


def counted_sides(ch, key):
    return [s for s in ch.sides.values() if s.exists or key in s.progress]


def side_status(s, key):
    return s.progress[key].status if key in s.progress else "not opened"


def side_summary(ch, key):
    """'done: A B; C: in progress, checkpoints 2 (b-01, c-01); not opened: D' for a chapter not completed."""
    sides = counted_sides(ch, key)
    done = [s.side for s in sides if side_status(s, key) == "completed"]
    new = [s.side for s in sides if side_status(s, key) == "not opened"]
    parts = [f"done: {' '.join(done)}"] if done else []
    for s in sides:
        st = side_status(s, key)
        if st not in ("completed", "not opened"):
            cps = s.progress[key].checkpoints
            parts.append(f"{s.side}: {st}" + (f", checkpoints {fmt_cps(cps)}" if cps else ""))
    if new:
        parts.append(f"not opened: {' '.join(new)}")
    return "; ".join(parts)


def fmt_session(slot):
    sess = slot.session
    name = f"{sess.title} ({sess.sid}, " if sess.title else f"{sess.sid} ("
    out = f"Resume: {name}{sess.side}-side), room {sess.room}"
    if sess.start_checkpoint:
        out += f", started from checkpoint room {sess.start_checkpoint}"
    out += f", {sess.deaths} death(s) this session"
    if sess.checkpoints:
        out += f"; {len(sess.checkpoints)} checkpoint(s) reached ({', '.join(fmt_cp(c) for c in sess.checkpoints)})"
    return out


# ---------------------------------------------------------------- views

def view_key(lib):
    """One slot loaded: its own view. Several: the "all" view (each mod from its furthest slot)."""
    return lib.slots[0].key if len(lib.slots) == 1 else ALL


def single_slot(lib, key):
    return lib.slots[0] if key != ALL or len(lib.slots) == 1 else None


def last_played(mod, slot):
    return bool(slot and slot.last_played_sid and mod.find_chapter(slot.last_played_sid))


def visible_mods(lib, key):
    slot = single_slot(lib, key)
    mods = [m for m in lib.mods if view_of(m, key).status != "not started"]
    return sorted(mods, key=lambda m: (not last_played(m, slot), -m.progress[key].ticks, m.name.lower()))


def ckpt_note(mod, v, slot):
    """The saved room for the last-played mod of a single slot, else the latest checkpoint."""
    if slot and slot.session and mod.find_chapter(slot.session.sid):
        return f" (room {slot.session.room})"
    lc = v.latest_checkpoint
    return f" (ckpt {lc['title'] or lc['room']})" if lc else ""


def note_of(user, key):
    return user.get(key, {}).get("note")


def mod_notes(mod, user):
    """Notes on the mod, or on any of its level sets (notes made before mods were the top level)."""
    return [n for n in (note_of(user, k) for k in [mod.id] + [ls.name for ls in mod.sets]) if n]


def mine_cell(fields):
    """The player's own fields, short: '4/5 · GM+1 · dropped'."""
    parts = [f"{fields['rating']}/5"] if fields.get("rating") else []
    parts += [fields["difficulty"]] if fields.get("difficulty") else []
    parts += ["dropped"] if fields.get("dropped") else []
    parts += [", ".join(fields["tags"])] if fields.get("tags") else []
    return " · ".join(parts)


# ---------------------------------------------------------------- overview

def render_text(lib, key, user, mods_info):
    slot = single_slot(lib, key)
    multi = slot is None
    mods = visible_mods(lib, key)
    rows = []  # (label, view, mod)
    for m in mods:
        v = m.progress[key]
        rows.append((mod_label(m, v), v, m))
        if len(m.sets) > 1:  # a collab: its level sets underneath (a mod with one set skips that level)
            for i, ls in enumerate(m.sets):
                branch = "└" if i == len(m.sets) - 1 else "├"
                rows.append((f"  {branch} {set_label(ls)}", view_of(ls, key), m))
    w = max([len(r[0]) for r in rows] + [3])
    slots_head = f"  {'Slot':<{SLOTS_WIDTH}}" if multi else ""
    mw = max([len(mine_cell(m.user)) for m in mods] + [0])
    mine_head = f"  {'Mine':<{max(mw, 4)}}" if mw else ""
    out = [f"{'Mod':<{w}}  {'Sides':<8}  {'Maps':<8}  {'Status':<15}  {'Deaths':>6}  {'Time':<9}  {'Berries':>7}"
           f"{slots_head}{mine_head}  Ckpts"]
    out.append("-" * (w + len(slots_head) + len(mine_head) + 82))
    for label, v, m in rows:
        is_mod = not label.startswith("  ")
        mark = " *" if is_mod and last_played(m, slot) else ""
        slots = f"  {slots_cell(v) if is_mod else '':<{SLOTS_WIDTH}}" if multi else ""
        mine = f"  {mine_cell(m.user) if is_mod else '':<{max(mw, 4)}}" if mw else ""
        ck = f"{v.open_checkpoints:>5}{ckpt_note(m, v, slot) if is_mod else ''}"
        out.append(f"{label:<{w}}  {sides_cell(v, m):<8}  {maps_cell(v, m):<8}  {v.status:<15}  {v.deaths:>6}  "
                   f"{fmt_time(v.ticks):<9}  {v.berries:>7}{slots}{mine}  {ck}{mark}".rstrip())
        if is_mod:
            for n in mod_notes(m, user):
                out.append(f"{'':<{w}}    note: {n}")
    out.append("")
    for s in lib.slots:
        if not multi and s.last_played_sid:
            out.append(f"* = contains your last-played map ({s.last_played_sid})")
        if s.session:
            out.append((f"Slot {s.key}: " if multi else "") + fmt_session(s))
    out.append("Sides = sides cleared out of all sides (crystal hearts don't count; --set shows them); "
               "Maps = chapters with every side cleared. A chapter's B and C sides count once each.")
    if multi:
        out.append(f"All {len(lib.slots)} slots: each mod shows the slot where you got furthest in it (Slot; "
                   "+N = other slots you played it in). Nothing is added up across slots.")
    views = [v for _, v, _ in rows]
    if any(not known(m) for _, _, m in rows):
        out.append("? = total unknown: that mod isn't in the Mods folder" + ("" if mods_info.maps else " (use --mods)")
                   + ", so only what you've opened is counted.")
    out.append("Ckpts = checkpoints reached in sides not yet completed. (room X) = your saved room; (ckpt X) = latest "
               "checkpoint listed. A save doesn't record how many a chapter has.")
    if any(not v.loaded for v in views):
        out.append("[not loaded] = Everest didn't load that mod the last time the game saved"
                   + (" (in any slot that has it)" if multi else "") + "; its progress is kept aside.")
    if multi:  # the list of unfinished chapters over all slots is too long to read; one mod or slot at a time
        out.append("For a mod's chapters and sides: --set NAME. For one slot's unfinished chapters: --slot N.")
        return "\n".join(out)

    shown = {m.id for m in mods} | {ls.name for m in mods for ls in m.sets}
    unfinished = [(m, [ch for ch in m.chapters() if view_of(ch, key).status == "in progress"]) for m in mods]
    unfinished = [(m, chs) for m, chs in unfinished if chs]
    if unfinished:
        out.append("\nOpened but not completed:")
        for m, chs in unfinished:
            out.append(f"  {mod_label(m, m.progress[key])}")
            for ch in sorted(chs, key=lambda c: -c.progress[key].ticks):
                shown.add(ch.sid)
                note = f"   <- {note_of(user, ch.sid)}" if note_of(user, ch.sid) else ""
                out.append(f"    - {chapter_label(ch)}  {side_summary(ch, key)}{note}")
    rest = {k: f["note"] for k, f in user.items() if f.get("note") and k not in shown}
    if rest:
        out.append("\nOther notes:")
        known_ids = {m.id for m in lib.mods} | {ls.name for m in lib.mods for ls in m.sets} | \
                    {ch.sid for m in lib.mods for ch in m.chapters()}
        for k, v in rest.items():
            out.append(f"  {k}: {v}" + ("" if k in known_ids else "  (not in save)"))
    return "\n".join(out)


def render_markdown(lib, key, user):
    multi = single_slot(lib, key) is None
    head = ["Mod", "Sides", "Maps", "Status", "Deaths", "Time", "Berries"] + ["Slot"] * multi + \
           ["Checkpoints", "Unfinished chapters", "Mine", "Notes"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    slot = single_slot(lib, key)
    for m in visible_mods(lib, key):
        v = m.progress[key]
        name = mod_label(m, v) + (" (last played)" if last_played(m, slot) else "")
        chs = ", ".join(f"{chapter_label(ch)} [{side_summary(ch, key)}]" for ch in m.chapters()
                        if view_of(ch, key).status == "in progress")
        sids = {m.id} | {ls.name for ls in m.sets} | {ch.sid for ch in m.chapters()}
        rn = "; ".join(f"{k}: {f['note']}" for k, f in user.items() if k in sids and f.get("note"))
        cells = [name, sides_cell(v, m), maps_cell(v, m), v.status, str(v.deaths), fmt_time(v.ticks), str(v.berries)] \
            + [slots_cell(v)] * multi + [f"{v.open_checkpoints}{ckpt_note(m, v, slot)}", chs, mine_cell(m.user), rn]
        out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- one mod

def find_mod(key, lib, view):
    """(mod, level set or None) that KEY names: a mod's ID or name, or a level set's ID or title.
    Exact first, else a unique case-insensitive substring; when several mods match, the one played wins."""
    targets = [(m, None, (m.id, m.name)) for m in lib.mods] + \
              [(m, ls, (ls.name, ls.title)) for m in lib.mods for ls in m.sets]
    low = key.lower()
    hits = [(m, ls) for m, ls, names in targets if key in names]
    hits = hits or [(m, ls) for m, ls, names in targets if any(n and low in n.lower() for n in names)]
    by_mod = {}
    for m, ls in hits:
        by_mod.setdefault(m.id, (m, []))[1].append(ls)
    if len(by_mod) > 1:
        played = {k: x for k, x in by_mod.items() if view_of(x[0], view).status != "not started"}
        by_mod = played if len(played) == 1 else by_mod
    if not by_mod:
        sys.exit(f"No mod or level set matches '{key}'.")
    if len(by_mod) > 1:
        sys.exit(f"'{key}' matches several mods, be more specific:\n  "
                 + "\n  ".join(f"{m.name} ({m.id})" for m, _ in list(by_mod.values())[:15]))
    m, sets = next(iter(by_mod.values()))
    only = sets[0] if len(sets) == 1 and sets[0] is not None and len(m.sets) > 1 else None
    return m, only


def side_cells(sv):
    if sv is None:
        return f"{'-':>6}  {'-':<9}  {'-':>7}"
    return f"{sv.deaths:>6}  {fmt_time(sv.ticks):<9}  {sv.berries:>7}  {fmt_cps(sv.checkpoints)}"


def render_mod(mod, key, lib, user, only_set=None):
    """Every chapter and side of one mod (or one of its level sets), including the ones never opened."""
    v = view_of(mod, key)
    head = mod_label(mod, v) + (f"  (mod ID: {mod.id})" if mod.id != mod.name else "")
    chapters = only_set.chapters if only_set else mod.chapters()
    n_prog = sum(view_of(ch, key).status == "in progress" for ch in chapters)
    n_new = sum(view_of(ch, key).status == "not opened" for ch in chapters)
    v = view_of(only_set, key) if only_set else v  # one level set of a collab: its own totals
    out = [head, f"Sides {sides_cell(v, mod)} done, chapters {maps_cell(v, mod)} done "
                 f"({n_prog} in progress, {n_new} not opened)"
           + (f", {v.hearts} heart(s) collected" if v.hearts else "")
]
    if also_played(mod, key):
        out.append(also_played(mod, key))
    if mine_cell(mod.user):
        out.append(f"Mine: {mine_cell(mod.user)}")
    for n in mod_notes(mod, user):
        out.append(f"note: {n}")
    one_chapter = len(mod.chapters()) == 1  # e.g. Sentient Forest: straight to its sides
    sets = [only_set] if only_set else mod.sets
    for ls in sets:
        if len(mod.sets) > 1:
            lv = view_of(ls, key)
            out.append(f"\n{ls.title + ' (' + ls.name + ')' if ls.title else ls.name}: "
                       f"sides {sides_cell(lv, mod)}, {lv.status}")
        chs = sorted(ls.chapters, key=lambda c: RANK.get(view_of(c, key).status, 3))
        labels = [(ch.title or ch.sid.rpartition("/")[2]) for ch in chs]
        w = 0 if one_chapter else max([len(x) for x in labels] + [7])
        lead = "" if one_chapter else f"{'Chapter':<{w}}  "
        out.append("")
        out.append(f"{lead}Side  {'Status':<17}  {'Deaths':>6}  {'Time':<9}  {'Berries':>7}  Checkpoints")
        out.append("-" * (len(lead) + 70))
        for ch, lab in zip(chs, labels):
            star = " *" if any(ch.sid == s.last_played_sid for s in lib.slots if key in (ALL, s.key)) else ""
            note = f"   <- {note_of(user, ch.sid)}" if note_of(user, ch.sid) else ""
            sides = counted_sides(ch, key) or list(ch.sides.values())
            if not sides:  # a chapter only known from another slot, with no side opened in this one
                out.append(f"{f'{lab:<{w}}  ' if lead else ''}{'-':<4}  {'not opened':<17}{star}{note}")
                continue
            for i, s in enumerate(sides):
                first = i == 0
                name = f"{lab if first else '':<{w}}  " if lead else ""
                sv = s.progress.get(key)
                st = side_status(s, key) + (" ♥" if sv and sv.heart else "")
                out.append(f"{name}{s.side:<4}  {st:<17}  {side_cells(sv)}"
                           f"{star if first else ''}{note if first else ''}".rstrip())
    out.append("")
    if any(ch.sid == s.last_played_sid for s in lib.slots for ch in chapters):
        out.append("* = your last-played map" + ("" if len(lib.slots) == 1 else " in a slot"))
    if v.hearts:
        out.append("♥ = crystal heart collected (not needed for a side to count as completed).")
    if not known(mod):
        out.append("Only chapters and sides you've opened are listed: this mod isn't in the Mods folder.")
    return "\n".join(out)


# ---------------------------------------------------------------- the player's own fields

def resolve_key(key, lib):
    """Match KEY to a mod ID or name: exact, else a unique substring. The player's fields are per mod."""
    titles = {m.id: m.name for m in lib.mods}
    if key in titles:
        return key
    low = key.lower()
    exact = [n for n, t in titles.items() if t and t.lower() == low]
    if len(exact) == 1:
        return exact[0]
    hits = [n for n, t in titles.items() if low in n.lower() or (t and low in t.lower())]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        sys.exit(f"'{key}' matches several mods, be more specific:\n  "
                 + "\n  ".join(f"{titles[n]} ({n})" if titles[n] and titles[n] != n else n for n in hits[:12]))
    sys.exit(f"No mod matches '{key}'.")


EDITS = {  # flag -> (store field, how to show it)
    "note": ("note", lambda v: v), "rate": ("rating", lambda v: f"{v}/5"),
    "difficulty": ("difficulty", lambda v: v), "rename": ("rename", lambda v: v),
}


def edit_field(store, lib, flag, key, value):
    field, show = EDITS[flag]
    key = resolve_key(key, lib)
    if field == "rating":
        if not value.isdigit() or not 0 <= int(value) <= 5:
            sys.exit("--rate takes 1 to 5, or 0 to clear.")
        value = int(value)
    else:
        value = value.strip()
    if field == "difficulty":  # "expert" is fine
        value = next((d for d in DIFFICULTIES if d.lower() == value.lower()), value)
    try:
        store.set_field(key, field, value)
    except ValueError as e:
        sys.exit(f"--{flag}: {e}.")
    print(f"Saved {field} for {key}: {show(value)}" if value else f"Cleared {field} for {key}")


def edit_tags(store, lib, key, tag, add):
    key = resolve_key(key, lib)
    have = store.user_fields().get(key, {}).get("tags", [])
    tag = clean_tag(tag)
    try:
        tags = store.set_tags(key, have + [tag] if add else [t for t in have if t != tag])
    except ValueError as e:
        sys.exit(f"--tag: {e}.")
    print(f"Tags for {key}: {', '.join(tags) or 'none'}")


# ---------------------------------------------------------------- main

def parse_args(argv):
    ap = argparse.ArgumentParser(description="Celeste mod progress from save files, without loading the mods. "
                                             "By default, all save slots: each mod from the slot that got "
                                             "furthest in it.")
    ap.add_argument("--slot", type=int, help="only this save slot")
    ap.add_argument("--all", action="store_true", help="all save slots, each mod from its furthest slot (the default)")
    ap.add_argument("--saves", help="path to the Saves folder")
    ap.add_argument("--file", help="path to a specific .celeste save file")
    ap.add_argument("--mods", nargs="?", const="auto", metavar="FOLDER",
                    help="read chapters, sides and titles from the Mods folder (default: next to Saves)")
    ap.add_argument("--no-mods", action="store_true", help="don't read the Mods folder, even if the config says to")
    ap.add_argument("--offline", action="store_true", help="don't download the mod list for GameBanana titles")
    ap.add_argument("--refresh-moddb", action="store_true", help="download the mod list now, even if the cache is fresh")
    ap.add_argument("--set", metavar="KEY", help="every chapter and side of one mod (name, ID, level set, or part)")
    ap.add_argument("--note", nargs=2, metavar=("KEY", "TEXT"),
                    help="set a note on a mod (empty TEXT removes it)")
    ap.add_argument("--rate", nargs=2, metavar=("KEY", "N"), help="rate how much you enjoyed a mod, 1 to 5; 0 clears")
    ap.add_argument("--difficulty", nargs=2, metavar=("KEY", "LEVEL"),
                    help=f"how hard a mod is for you: {', '.join(DIFFICULTIES)} (empty clears)")
    ap.add_argument("--tag", nargs=2, metavar=("KEY", "TAG"), help="add a tag of your own to a mod")
    ap.add_argument("--untag", nargs=2, metavar=("KEY", "TAG"), help="remove a tag from a mod")
    ap.add_argument("--drop", metavar="KEY", help="mark a mod as dropped")
    ap.add_argument("--undrop", metavar="KEY", help="unmark a dropped mod")
    ap.add_argument("--rename", nargs=2, metavar=("KEY", "NAME"),
                    help="show a mod under your own name (empty NAME goes back to the GameBanana title)")
    ap.add_argument("--import-notes", metavar="FILE", help="import notes from an old celeste_notes.json")
    ap.add_argument("--markdown", metavar="FILE", help="also write a markdown table to this file")
    ap.add_argument("--json", metavar="FILE", help="write everything parsed as JSON to FILE ('-' for stdout)")
    ap.add_argument("--dump", action="store_true", help="print the XML structure of one slot and exit")
    ap.add_argument("--serve", nargs="?", type=int, const=8765, metavar="PORT",
                    help="open the tracker as a page in your browser, at http://localhost:PORT (default 8765)")
    ap.add_argument("--config", help=f"config file (default: {config_path()}); the store (tracker.db) and the mod "
                                     "list cache sit next to it")
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

    if args.file or args.slot is not None:
        path = find_save(args.file, saves, args.slot or 0)
        slot_paths = [(slot_number(path), path)]
    else:
        saves_dir = find_saves_dir(saves)
        if not saves_dir or not saves_dir.is_dir():
            sys.exit("Could not find the Saves folder. Use --saves <folder>, --slot N or --file <path>.")
        slot_paths = list_slots(saves_dir)
        if not slot_paths:
            sys.exit(f"No save slots (N.celeste) in {saves_dir}.")
    if args.dump:
        if len(slot_paths) != 1:
            sys.exit("--dump needs --slot N or --file <path>.")
        dump(slot_paths[0][1])
        return

    store = Store(cfg_file.parent / "tracker.db")
    if args.import_notes:
        print(f"Imported {store.import_notes(args.import_notes)} note(s) from {args.import_notes}.")
        return
    if not args.config:  # the real store, not a test's: bring over notes from before the store, once
        n = store.import_old_notes_once()
        if n:
            print(f"Moved {n} note(s) from celeste_notes.json into {store.path} (the old file is kept).",
                  file=sys.stderr)

    mods_dir = mods_dir_for(slot_paths[0][1], mods_arg) if mods_arg else None
    if args.serve is not None:
        from .web.server import App, serve
        titles = load_titles(cfg_file.parent / "moddb.json", offline=args.offline, refresh=args.refresh_moddb) \
            if mods_dir else {}
        all_slots = not (args.file or args.slot is not None)
        serve(App(store, mods_dir, titles, slot_paths[0][1].parent if all_slots else None, slot_paths), args.serve)
        return
    mods = load_mods(mods_dir, store.mod_cache())
    titles = load_titles(cfg_file.parent / "moddb.json", offline=args.offline, refresh=args.refresh_moddb) \
        if mods.maps else {}
    lib = load_library(slot_paths, mods, titles, store.user_fields())
    key = view_key(lib)

    for flag in ("note", "rate", "difficulty", "rename"):
        if getattr(args, flag):
            edit_field(store, lib, flag, *getattr(args, flag))
            return
    if args.tag or args.untag:
        edit_tags(store, lib, *(args.tag or args.untag), add=bool(args.tag))
        return
    if args.drop or args.undrop:
        k = resolve_key(args.drop or args.undrop, lib)
        store.set_field(k, "dropped", bool(args.drop))
        print(f"{'Marked' if args.drop else 'Unmarked'} {k} as dropped")
        return
    if args.json == "-":
        print(to_json(lib, mods))
        return
    user = store.user_fields()
    if args.set:
        mod, only = find_mod(args.set, lib, key)
        print(render_mod(mod, key, lib, user, only))
        return
    if not visible_mods(lib, key):
        print(f"No progress found in {slot_paths[0][1]}. Try --dump to inspect the file structure.")
        return

    if len(lib.slots) > 1:
        print(f"Saves: {slot_paths[0][1].parent} ({len(lib.slots)} slots; each mod from its furthest slot)")
    else:
        print(f"Save: {slot_paths[0][1]}")
    if mods.source:
        named = sum(1 for m in lib.mods if m.name_source == "gamebanana")
        print(f"Mods: {mods.source} ({mods.summary()}; {named} named from GameBanana)")
    print()
    print(render_text(lib, key, user, mods))

    if args.markdown:
        Path(args.markdown).write_text(render_markdown(lib, key, user), encoding="utf-8")
        print(f"\nMarkdown written to {args.markdown}")
    if args.json:
        Path(args.json).write_text(to_json(lib, mods), encoding="utf-8")
        print(f"\nJSON written to {args.json}")
