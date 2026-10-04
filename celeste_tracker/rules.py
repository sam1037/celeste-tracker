"""Completion rules from doc/PRD.md ("Definition of completed"). The only place statuses are decided.

- Side completed: cleared and its heart collected, or cleared if the side has no heart.
  While it's unknown whether a side has a heart (mods, until map .bin parsing), a cleared side
  without its heart is "cleared, no heart", never "completed": the tool doesn't claim more than the save shows.
- Map completed: every side it has is completed.
- Level set completed: every map in the set is completed.
"""

SIDE_STATUSES = ("completed", "cleared, no heart", "in progress", "not opened")
MAP_STATUSES = ("completed", "in progress", "not opened")
SET_STATUSES = ("complete", "all opened done", "hearts missing", "in progress", "started", "not started")


def side_status(s):
    if not s.opened:
        return "not opened"
    if s.cleared and (s.heart or s.has_heart is False):
        return "completed"
    if s.cleared:
        return "cleared, no heart"
    return "in progress"


def map_status(m):
    statuses = [s.status for s in m.sides.values()]
    if statuses and all(st == "completed" for st in statuses):
        return "completed"
    if any(st != "not opened" for st in statuses):
        return "in progress"
    return "not opened"


def set_status(ls):
    if not any(m.status != "not opened" for m in ls.maps):
        return "not started"
    if ls.sides_done == ls.sides_total:
        # Without mod files, the totals only cover what was opened.
        return "complete" if ls.sides_known else "all opened done"
    if ls.sides_done + ls.sides_no_heart == ls.sides_total:
        return "hearts missing"
    return "in progress" if ls.sides_done else "started"


def apply_set(ls):
    sides = []
    for m in ls.maps:
        for s in m.sides.values():
            s.status = side_status(s)
            sides.append((m, s))
        m.status = map_status(m)
    counted = [m for m in ls.maps if m.sides]  # a map with no known or opened side tells us nothing
    ls.sides_total = len(sides)
    ls.sides_done = sum(s.status == "completed" for _, s in sides)
    ls.sides_no_heart = sum(s.status == "cleared, no heart" for _, s in sides)
    ls.maps_total = len(counted)
    ls.maps_done = sum(m.status == "completed" for m in counted)
    ls.deaths = sum(s.deaths for _, s in sides)
    ls.ticks = sum(s.ticks for _, s in sides)
    ls.berries = sum(s.berries for _, s in sides)
    unfinished = [(m, s) for m, s in sides if s.status != "completed" and s.checkpoints]
    ls.open_checkpoints = sum(len(s.checkpoints) for _, s in unfinished)
    ls.latest_checkpoint = None
    if unfinished:
        # From the unfinished side with checkpoints you've played longest: the last one the save lists.
        m, s = max(unfinished, key=lambda ms: ms[1].ticks)
        cp = s.checkpoints[-1]
        ls.latest_checkpoint = {"sid": m.sid, "side": s.side, "room": cp.room, "title": cp.title}
    ls.status = set_status(ls)


def apply(slot):
    for ls in slot.sets:
        apply_set(ls)
    # Last-played set first, then by time played.
    slot.sets.sort(key=lambda ls: (not ls.last_played, -ls.ticks))
    return slot
