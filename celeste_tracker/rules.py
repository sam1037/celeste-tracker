"""Completion rules from doc/PRD.md ("Definition of completed"). The only place statuses are decided.

- Side completed: cleared. The crystal heart doesn't count: many sides have none (lobbies, prologues), and for
  mods the save can't tell. Hearts collected are counted separately (View.hearts), as information.
- Chapter completed: every side it has is completed. Level set / mod completed: every chapter in it is.
- All slots combined (doc/DESIGN.md): a side's status is the best of its per-slot statuses (each decided
  inside one slot); deaths, time and berries add up; best time and best deaths are the best of any slot.
"""
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


def combine_side(views):
    """The "all" view of a side from its per-slot views."""
    best = min(views.values(), key=lambda v: SIDE_STATUSES.index(v.status))
    longest = max(views.values(), key=lambda v: v.ticks)
    cleared_runs = [v for v in views.values() if v.best_ticks]
    return count_side(View(
        status=best.status, cleared=best.cleared, heart=any(v.heart for v in views.values()),
        deaths=sum(v.deaths for v in views.values()), ticks=sum(v.ticks for v in views.values()),
        berries=sum(v.berries for v in views.values()),
        best_ticks=min((v.best_ticks for v in cleared_runs), default=0),
        best_deaths=min((v.best_deaths for v in cleared_runs), default=0),
        checkpoints=longest.checkpoints,  # no dates in the save: the slot with the most time on it
        slots=list(views)))


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
            if sv is None:
                continue
            opened += 1
            slots.update(sv.slots)
            v.sides_done += sv.sides_done
            v.hearts += sv.hearts
            v.deaths += sv.deaths
            v.ticks += sv.ticks
            v.berries += sv.berries
            v.open_checkpoints += sv.open_checkpoints
            if sv.status != "completed" and sv.checkpoints:
                unfinished.append((ch, s, sv))
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
                if per_slot:
                    s.progress[ALL] = combine_side(per_slot)
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
        mod.progress = {}
        for k in mod_keys:
            v, opened = rollup(mod.chapters(), k, order)
            v.status = set_status(v, opened, known)
            v.loaded = any(ls.progress[k].loaded for ls in mod.sets if k in ls.progress and ls.progress[k].slots) \
                or not v.slots
            mod.progress[k] = v
    return lib
