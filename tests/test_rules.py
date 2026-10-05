from celeste_tracker.core import load_library
from celeste_tracker.mods import ModInfo
from celeste_tracker.model import View
from celeste_tracker.rules import ALL, set_status, side_status

from conftest import SLOTS


def lib1(mods, titles=None):
    return load_library([(1, SLOTS / "1.celeste")], mods, titles)


def mod(lib, mod_id):
    return next(m for m in lib.mods if m.id == mod_id)


def statuses(ch, key):
    return {k: (s.progress[key].status if key in s.progress else "not opened") for k, s in ch.sides.items()}


def test_side_status_is_cleared_hearts_dont_count():
    assert side_status(View()) == "in progress"  # a view exists only for opened sides
    assert side_status(View(cleared=True, heart=True)) == "completed"
    assert side_status(View(cleared=True)) == "completed"  # e.g. vanilla 1A cleared without its hidden heart
    assert side_status(View(heart=True)) == "in progress"  # heart taken, chapter not finished


def test_set_status():
    assert set_status(View(sides_done=2, sides_total=2), 2, True) == "complete"
    assert set_status(View(sides_done=2, sides_total=2), 2, False) == "all opened done"
    assert set_status(View(sides_done=1, sides_total=3), 1, True) == "in progress"
    assert set_status(View(sides_total=3), 1, True) == "started"
    assert set_status(View(sides_total=3), 0, True) == "not started"


def test_chapter_with_three_sides(mods):
    m = mod(lib1(mods), "Sides Mod")
    assert (m.name, m.name_source) == ("The Forest", "map title")  # one chapter, no GameBanana title
    forest = m.chapters()[0]
    assert statuses(forest, "1") == {"A": "completed", "B": "completed", "C": "in progress"}
    assert forest.progress["1"].status == "in progress"
    v = m.progress["1"]
    assert (v.sides_done, v.sides_total, v.maps_done, v.maps_total) == (2, 3, 0, 1)
    assert v.status == "in progress"
    assert v.latest_checkpoint == {"sid": "Test/Sides/Forest", "side": "C", "room": "c-01", "title": "Deep Woods"}
    assert v.open_checkpoints == 1  # A's checkpoint doesn't count: A is completed
    assert v.deaths == 287 + 1300 + 288


def test_gamebanana_title_wins(mods):
    m = mod(lib1(mods, {"Sides Mod": {"title": "Forest Journey", "author": "x"}}), "Sides Mod")
    assert (m.name, m.name_source, m.gamebanana_title) == ("Forest Journey", "gamebanana", "Forest Journey")


def test_collab_and_its_add_on_are_two_mods(mods):
    lib = lib1(mods)
    collab = mod(lib, "Collab")
    st = {ch.sid.rpartition("/")[2]: ch.progress["1"].status for ch in collab.chapters()}
    assert st == {"Lobby": "completed", "M1": "completed", "M2": "not opened", "M3-D": "not opened"}
    assert statuses(collab.find_chapter("Test/Collab/Lobby"), "1") == {"A": "completed"}  # cleared, no heart
    v = collab.progress["1"]
    # The save's empty B/C placeholders are dropped: these chapters only have an A side.
    assert (v.sides_done, v.hearts, v.sides_total, v.maps_done, v.maps_total) == (2, 1, 4, 2, 4)
    assert v.status == "in progress"
    addon = mod(lib, "Collab D Side")
    assert [ch.sid for ch in addon.chapters()] == ["Test/Collab/Extra-D"]
    assert addon.progress[ALL].status == "not started"


def test_vanilla_uses_built_in_list(mods):
    m = mod(lib1(mods), "Celeste")
    v = m.progress["1"]
    assert (v.sides_total, v.maps_total) == (27, 11)  # all chapters, though the save lists two
    assert statuses(m.find_chapter("Celeste/0-Intro"), "1") == {"A": "completed"}  # Prologue has no heart
    assert statuses(m.find_chapter("Celeste/1-ForsakenCity"), "1") == \
        {"A": "completed", "B": "in progress", "C": "not opened"}
    assert m.find_chapter("Celeste/LostLevels").title == "Farewell"
    assert (v.sides_done, v.maps_done, v.status) == (2, 1, "in progress")


def test_unknown_mod_and_b_c_only_chapter(mods):
    lib = lib1(mods)
    gone = mod(lib, "Gone/Old")  # not in the Mods folder: a mod named after its level set
    assert not gone.found and gone.name == "Gone/Old"
    assert (gone.progress["1"].sides_done, gone.progress["1"].sides_total) == (0, 1)
    assert gone.progress["1"].status == "started" and not gone.progress["1"].loaded  # in the recycle bin
    blizzard = mod(lib, "Blizzard").chapters()[0]
    assert statuses(blizzard, "1") == {"B": "in progress", "C": "not opened"}


def test_without_mods_only_opened_sides_count():
    m = mod(lib1(ModInfo()), "Test/Sides")
    assert not m.found
    assert (m.progress["1"].sides_done, m.progress["1"].sides_total) == (2, 3)  # all three were opened


def test_slots_combined(mods):
    lib = load_library([(1, SLOTS / "1.celeste"), (2, SLOTS / "2.celeste")], mods)
    collab = mod(lib, "Collab")
    assert collab.progress["1"].sides_done == 2 and collab.progress["2"].sides_done == 1
    v = collab.progress[ALL]
    assert (v.sides_done, v.sides_total, v.slots) == (3, 4, ["1", "2"])  # Lobby, M1 in slot 1; M2 in slot 2
    prologue = mod(lib, "Celeste").find_chapter("Celeste/0-Intro").sides["A"]
    assert list(prologue.progress) == ["1", "2", ALL] and prologue.progress[ALL].slots == ["1", "2"]


def test_best_status_is_decided_per_slot(tmp_path, mods):
    """Cleared in one slot, heart only in another: completed (clearing is what counts), heart collected."""
    def save(path, cleared, heart, deaths):
        path.write_text(f'''<SaveData><Name>x</Name><LevelSets><LevelSetStats Name="Test/Sides"><Areas>
            <AreaStats SID="Test/Sides/Forest"><Modes>
            <AreaModeStats Completed="{cleared}" HeartGem="{heart}" Deaths="{deaths}" TimePlayed="10" BestTime="5"
              BestDeaths="{deaths}" TotalStrawberries="1"><Checkpoints /></AreaModeStats>
            </Modes></AreaStats></Areas></LevelSetStats></LevelSets></SaveData>''')
        return path
    lib = load_library([(1, save(tmp_path / "1.celeste", "true", "false", 3)),
                        (2, save(tmp_path / "2.celeste", "false", "true", 4))], mods)
    a = mod(lib, "Sides Mod").chapters()[0].sides["A"]
    assert a.progress["1"].status == "completed" and a.progress["2"].status == "in progress"
    assert a.progress[ALL].status == "completed" and a.progress[ALL].heart
    assert (a.progress[ALL].deaths, a.progress[ALL].berries, a.progress[ALL].best_deaths) == (7, 2, 3)


def test_view_keys_are_in_slot_order(mods):
    lib = load_library([(2, SLOTS / "2.celeste"), (1, SLOTS / "1.celeste")], mods)
    assert list(mod(lib, "Collab").progress) == ["2", "1", ALL]  # the order the slots were given in
