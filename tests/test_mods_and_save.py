from celeste_tracker.mods import mod_name, split_side
from celeste_tracker.paths import list_slots
from celeste_tracker.save import parse_save

from conftest import SLOTS


def test_split_side():
    assert split_side("Set/Map") == ("Set/Map", "A")
    assert split_side("Set/Map-B") == ("Set/Map", "B")
    assert split_side("Set/Map-C") == ("Set/Map", "C")
    assert split_side("Set/Map-D") == ("Set/Map-D", "A")   # not a side, a map of its own
    assert split_side("Set/Map-b") == ("Set/Map-b", "A")   # only uppercase, like Everest


def test_mod_name():
    assert mod_name(b"- Name: OmoriPack\n  Version: 1.0.0\n") == "OmoriPack"
    assert mod_name(b"- DLL: x.dll\n  Name: 'Sentient Forest'\n  Dependencies:\n    - Name: Everest\n") == "Sentient Forest"
    assert mod_name(b"Dependencies:\n    - Name: Everest\n") == ""


def test_scan_folds_b_and_c_sides(mods):
    assert mods.maps["Test/Sides"] == {"Test/Sides/Forest": {"A", "B", "C"}}
    assert mods.sides("Test/Sides/Forest") == "ABC"
    assert mods.maps["Test/Blizzard"] == {"Test/Blizzard/1-blizzard": {"B", "C"}}
    assert set(mods.maps["Test/Collab"]) == {"Test/Collab/Lobby", "Test/Collab/M1", "Test/Collab/M2",
                                              "Test/Collab/M3-D", "Test/Collab/Extra-D"}


def test_scan_mod_names(mods):
    assert mods.mod_of["Test/Sides"] == "Sides Mod"
    assert mods.mod_of["Test/Collab"] == "Collab"      # zip name; the add-on adds fewer maps
    assert mods.mod_of["Test/Blizzard"] == "Blizzard"  # unzipped folder


def test_titles(mods):
    assert mods.title("Test/Sides") == "Side Set"
    assert mods.title("Test/Sides/Forest") == "The Forest"  # formatting tags stripped
    assert mods.checkpoint("Test/Sides/Forest", "c-01") == "Deep Woods"
    assert mods.title("Nope/Nope") == ""


def test_list_slots_skips_other_files():
    assert [n for n, _ in list_slots(SLOTS)] == [1, 2]


def test_parse_save():
    raw = parse_save(SLOTS / "1.celeste")
    assert raw["name"] == "fixture"
    assert raw["last_area"] == "Test/Sides/Forest"  # LastArea_Safe wins over vanilla's LastArea
    names = [(s["name"], s["loaded"], s["vanilla"]) for s in raw["sets"]]
    assert names == [("Celeste (vanilla)", True, True), ("Test/Sides", True, False), ("Test/Collab", True, False),
                     ("Gone/Old", False, False), ("Test/Blizzard", False, False)]
    forest = raw["sets"][1]["areas"][0]
    assert [s["side"] for s in forest["sides"]] == ["A", "B", "C"]
    assert forest["sides"][2]["checkpoints"] == ["c-01"]
    assert raw["session"] == {"sid": "Test/Sides/Forest", "side": "C", "room": "c-02",
                              "start_checkpoint": "c-01", "deaths": 4}
