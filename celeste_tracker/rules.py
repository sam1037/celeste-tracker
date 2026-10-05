"""Completion rules from doc/PRD.md ("Definition of completed"). The only place statuses are decided.

- Side completed: cleared. The crystal heart doesn't count: many sides have none (lobbies, prologues), and for
  mods the save can't tell. Hearts collected are counted separately (View.hearts), as information.
- Chapter completed: every side it has is completed. Level set / mod completed: every chapter in it is.
- All slots (doc/DESIGN.md): each mod shows the slot that got furthest in it (furthest_slot). Every node's
  "all" view is a copy of that slot's view, so nothing is added up or mixed across slots.
"""
from dataclasses import replace

from .model import View

ALL = "all"
SIDE_STATUSES = ("completed", "in progress", "not opened")  # best first
MAP_STATUSES = ("completed", "in progress", "not opened")
SET_STATUSES = ("complete", "all opened done", "in progress", "started", "not started")


def side_status(v):
    """Status of a side in a view that exists, i.e. the side was opened in that slot."""
    return "completed" if v.cleared else "in progress"


def count_side(v):
    v.sides_total = 1
    v.sides_done = int(v.status == "completed")
    v.hearts = int(v.heart)
    v.open_checkpoints = 0 if v.status == "completed" else len(v.checkpoints)
    return v


def furthest_slot(views, opened):
    """The slot that got furthest in a mod, from its per-slot views: most sides completed, then most sides
    opened, then most checkpoints reached on unfinished sides, then most time played. None if never played."""
    played = [k for k, v in views.items() if opened[k]]
    return max(played, key=lambda k: (views[k].sides_done, opened[k], views[k].open_checkpoints, views[k].ticks),
               default=None)


def rollup(chapters, key, order):
    """Totals over chapters for one view key. A side counts if it exists, or if it was opened in this view
    (sides of unknown mods are only known once opened)."""
    v = View()
    slots, opened, unfinished = set(), 0, []
    for ch in chapters:
        counted = [s for s in ch.sides.values() if s.exists or key in s.progress]
        if not counted:
            continue
        views = [s.progress.get(key) for s in counted]
        v.maps_total += 1
        v.maps_done += all(sv and sv.status == "completed" for sv in views)
        for s, sv in zip(counted, views):
            v.sides_total += 1
            letter = v.by_side.setdefault(s.side, [0, 0])
            letter[1] += 1
            if sv is None:
                continue
            opened += 1
            slots.update(sv.slots)
            v.sides_done += sv.sides_done
            letter[0] += sv.sides_done
            v.hearts += sv.hearts
            v.deaths += sv.deaths
            v.ticks += sv.ticks
            v.berries += sv.berries
            v.open_checkpoints += sv.open_checkpoints
            if sv.status != "completed" and sv.checkpoints:
                unfinished.append((ch, s, sv))
    v.by_side = {k: v.by_side[k] for k in sorted(v.by_side)}  # A, B, C, whatever order the chapters came in
    if unfinished:
        # From the unfinished side with checkpoints you've played longest: the last one the save lists.
        ch, s, sv = max(unfinished, key=lambda x: x[2].ticks)
        cp = sv.checkpoints[-1]
        v.latest_checkpoint = {"sid": ch.sid, "side": s.side, "room": cp.room, "title": cp.title}
    v.slots = sorted(slots, key=order)
    return v, opened


def chapter_status(v, opened):
    if v.maps_total and v.maps_done == v.maps_total:
        return "completed"
    return "in progress" if opened else "not opened"


def set_status(v, opened, known):
    if not opened:
        return "not started"
    if v.sides_done == v.sides_total:
        return "complete" if known else "all opened done"  # without mod files, totals only cover what was opened
    return "in progress" if v.sides_done else "started"


def keys_of(chapters):
    """View keys with any progress under these chapters, plus "all"."""
    keys = {ALL}
    for ch in chapters:
        for s in ch.sides.values():
            keys.update(s.progress)
    return keys


def apply(lib):
    index = {s.key: i for i, s in enumerate(lib.slots)}
    order = lambda key: index.get(key, len(index))
    not_loaded = {s.key: set(s.not_loaded) for s in lib.slots}
    for mod in lib.mods:
        known = mod.found or mod.vanilla
        for ch in mod.chapters():
            for s in ch.sides.values():
                per_slot = {k: v for k, v in s.progress.items() if k != ALL}
                for v in per_slot.values():
                    v.status = side_status(v)
                    count_side(v)
                s.progress = {k: per_slot[k] for k in sorted(per_slot, key=order)}
        # Every chapter and level set gets all of the mod's keys, so what wasn't played in a slot still shows
        # (as not opened / not started). Sides only have views where they were opened.
        mod_keys = sorted(keys_of(mod.chapters()), key=order)  # slots in order, then "all"
        for ch in mod.chapters():
            ch.progress = {}
            for k in mod_keys:
                v, opened = rollup([ch], k, order)
                v.status = chapter_status(v, opened)
                ch.progress[k] = v
        for ls in mod.sets:
            ls.progress = {}
            for k in mod_keys:
                v, opened = rollup(ls.chapters, k, order)
                v.status = set_status(v, opened, known)
                in_bin = [sl for sl in v.slots if ls.name in not_loaded[sl]]
                v.loaded = mod.vanilla or not v.slots or len(in_bin) < len(v.slots)
                ls.progress[k] = v
        mod.progress, opened_in = {}, {}
        for k in mod_keys:
            v, opened_in[k] = rollup(mod.chapters(), k, order)
            v.status = set_status(v, opened_in[k], known)
            v.loaded = any(ls.progress[k].loaded for ls in mod.sets if k in ls.progress and ls.progress[k].slots) \
                or not v.slots
            mod.progress[k] = v
        show_furthest_slot(mod, mod_keys, opened_in)
    return lib


def show_furthest_slot(mod, keys, opened_in):
    """Make every node's "all" view a copy of the mod's furthest slot, keeping the list of slots it was played in.
    A mod never played keeps its "all" view from rollup (not started, with the catalog's totals)."""
    slot_keys = [k for k in keys if k != ALL]
    best = furthest_slot({k: mod.progress[k] for k in slot_keys}, opened_in)
    if best is None:
        return
    for node in [mod, *mod.sets, *mod.chapters()]:
        played = [k for k in slot_keys if node.progress[k].slots]
        node.progress[ALL] = replace(node.progress[best], slot=best, slots=played)
    for ch in mod.chapters():
        for s in ch.sides.values():
            s.progress.pop(ALL, None)
            if best in s.progress:  # a side not opened in that slot has no "all" view: not opened
                s.progress[ALL] = replace(s.progress[best], slot=best, slots=list(s.progress))
