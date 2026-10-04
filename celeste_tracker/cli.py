"""Command line: argument parsing and text / markdown rendering."""
import argparse
import sys
from pathlib import Path

from .mods import ModInfo, load_mods
from .paths import find_save
from .rules import summarize
from .save import dump, parse_save
from .store import DEFAULT_NOTES, load_json, save_json

TICKS_PER_SECOND = 10_000_000
NOT_LOADED = " [not loaded]"


def fmt_time(ticks):
    secs = ticks // TICKS_PER_SECOND
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


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


# ---------------------------------------------------------------- main

def main(argv=None):
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
    ap.add_argument("--notes", default=str(DEFAULT_NOTES), help="notes file")
    args = ap.parse_args(argv)

    path = find_save(args.file, args.saves, args.slot)
    if args.dump:
        dump(path)
        return

    sets, last_area, session = parse_save(path)
    mods = load_mods(args.mods, path)
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
