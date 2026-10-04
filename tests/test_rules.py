from celeste_tracker.core import load_slot
from celeste_tracker.mods import ModInfo
from celeste_tracker.model import LevelSet, Map, Side
from celeste_tracker.rules import apply_set, side_status

from conftest import SLOTS


def by_name(slot):
    return {ls.name: ls for ls in slot.sets}


def statuses(m):
    return {k: s.status for k, s in m.sides.items()}


def test_side_status():
    assert side_status(Side("A", True, None)) == "not opened"
    assert side_status(Side("A", True, None, opened=True)) == "in progress"
    assert side_status(Side("A", True, None, opened=True, cleared=True, heart=True)) == "completed"
    # Unknown whether there is a heart: cleared alone isn't enough.
    assert side_status(Side("A", True, None, opened=True, cleared=True)) == "cleared, no heart"
    # Known to have no heart: cleared is enough (PRD).
    assert side_status(Side("A", True, False, opened=True, cleared=True)) == "completed"
    # Known to have a heart, not collected.
    assert side_status(Side("A", True, True, opened=True, cleared=True)) == "cleared, no heart"


def test_map_with_three_sides(mods):
    sets = by_name(load_slot(SLOTS / "1.celeste", mods, 1))
    ls = sets["Test/Sides"]
    forest = ls.maps[0]
    assert forest.title == "The Forest"
    assert statuses(forest) == {"A": "completed", "B": "completed", "C": "in progress"}
    assert forest.status == "in progress"
    assert (ls.sides_done, ls.sides_total, ls.maps_done, ls.maps_total) == (2, 3, 0, 1)
    assert ls.status == "in progress"
    assert ls.mod_name == "Sides Mod" and ls.title == "Side Set"
    assert ls.latest_checkpoint == {"sid": "Test/Sides/Forest", "side": "C", "room": "c-01", "title": "Deep Woods"}
    assert ls.open_checkpoints == 1  # A's checkpoint doesn't count: A is completed
    assert ls.deaths == 287 + 1300 + 288


def test_collab_counts_unopened_maps(mods):
    ls = by_name(load_slot(SLOTS / "1.celeste", mods, 1))["Test/Collab"]
    st = {m.sid.rpartition("/")[2]: m.status for m in ls.maps}
    assert st == {"Lobby": "in progress", "M1": "completed", "M2": "not opened", "M3-D": "not opened",
                  "Extra-D": "not opened"}
    assert statuses(ls.find_map("Test/Collab/Lobby")) == {"A": "cleared, no heart"}
    # The save's empty B/C placeholders are dropped: these maps only have an A side.
    assert (ls.sides_done, ls.sides_no_heart, ls.sides_total) == (1, 1, 5)
    assert (ls.maps_done, ls.maps_total) == (1, 5)
    assert ls.status == "in progress"


def test_vanilla_uses_built_in_list(mods):
    ls = by_name(load_slot(SLOTS / "1.celeste", mods, 1))["Celeste (vanilla)"]
    assert (ls.sides_total, ls.maps_total) == (27, 11)  # all chapters, though the save lists two
    assert statuses(ls.find_map("Celeste/0-Intro")) == {"A": "completed"}  # Prologue has no heart
    assert statuses(ls.find_map("Celeste/1-ForsakenCity")) == {"A": "completed", "B": "in progress", "C": "not opened"}
    assert ls.find_map("Celeste/LostLevels").title == "Farewell"
    assert (ls.sides_done, ls.maps_done) == (2, 1)
    assert ls.status == "in progress"


def test_unknown_and_b_c_only_maps(mods):
    sets = by_name(load_slot(SLOTS / "1.celeste", mods, 1))
    gone = sets["Gone/Old"]
    assert not gone.sides_known and not gone.loaded
    assert (gone.sides_done, gone.sides_total) == (0, 1)
    assert gone.status == "started"
    blizzard = sets["Test/Blizzard"].maps[0]
    assert statuses(blizzard) == {"B": "in progress", "C": "not opened"}


def test_without_mods_only_opened_sides_count():
    ls = by_name(load_slot(SLOTS / "1.celeste", ModInfo(), 1))["Test/Sides"]
    assert not ls.sides_known
    assert (ls.sides_done, ls.sides_total) == (2, 3)  # all three were opened
    assert ls.title == "" and ls.mod_name == ""


def test_slot_session_and_order(mods):
    slot = load_slot(SLOTS / "1.celeste", mods, 1)
    assert slot.sets[0].name == "Test/Sides" and slot.sets[0].last_played
    assert slot.session.side == "C" and slot.session.room == "c-02"
    assert [c.room for c in slot.session.checkpoints] == ["c-01"]
    assert slot.session.title == "The Forest"


def set_with(*sides):
    ls = LevelSet("X", "", "", True, False, True, [Map("X/m", "", {s.side: s for s in sides})])
    apply_set(ls)
    return ls


def test_set_statuses():
    done = dict(opened=True, cleared=True, heart=True)
    assert set_with(Side("A", True, None, **done)).status == "complete"
    assert set_with(Side("A", True, None, **done), Side("B", True, None, opened=True, cleared=True)).status \
        == "hearts missing"
    assert set_with(Side("A", True, None, **done), Side("B", True, None)).status == "in progress"
    assert set_with(Side("A", True, None, opened=True), Side("B", True, None)).status == "started"
    assert set_with(Side("A", True, None)).status == "not started"
