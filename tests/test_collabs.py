"""Collab conventions: titles written on the line under their dialog key.
Everything here is made up; the layout copies what real collabs do (doc/NOTES.md)."""
import pytest

from celeste_tracker.mods import parse_dialog, scan_mods

from conftest import write_zip

# Like Strawberry Jam: map files are named after their authors, each title is on the line under its key,
# and the author and credits keys follow it (credits run over several lines).
JAM_DIALOG = """\
# Jam dialog
Jam_0_Gyms=
  Jam - Gyms
Jam_1_Beginner=
  Jam - Beginner

Jam_0_Gyms_1_Beginner=
  Beginner Gym
Jam_0_Lobbies_1_Beginner=
  Beginner Lobby
Jam_1_Beginner_alice=
  Sunken {#ff0000}Garden{#}
Jam_1_Beginner_alice_author=
  by alice
Jam_1_Beginner_alice_collabcredits=
  Code:{# 2a2a2a} carol{#}
  Music:{# 2a2a2a} dave{#}
Jam_1_Beginner_bob= Quiet Cliffs
Jam_1_Beginner_bob_author=
  by bob
Jam_1_Beginner_bob=
  Not This One
"""


def side(cleared, deaths=1):
    return (f'<AreaModeStats Completed="{cleared}" HeartGem="{cleared}" Deaths="{deaths}" TimePlayed="10">'
            f'<Checkpoints /></AreaModeStats>')


def jam_save(path):
    """Lobby and both maps cleared; the gym opened but not cleared, as gyms are."""
    def level_set(name, *maps):
        areas = "".join(f'<AreaStats SID="{name}/{m}"><Modes>{side(c)}</Modes></AreaStats>' for m, c in maps)
        return f'<LevelSetStats Name="{name}"><Areas>{areas}</Areas></LevelSetStats>'
    path.write_text("<SaveData><Name>jam</Name><LevelSets>"
                    + level_set("Jam/0-Gyms", ("1-Beginner", "false"))
                    + level_set("Jam/0-Lobbies", ("1-Beginner", "true"))
                    + level_set("Jam/1-Beginner", ("alice", "true"), ("bob", "true"))
                    + "</LevelSets></SaveData>")
    return path


@pytest.fixture
def jam(tmp_path):
    d = tmp_path / "Mods"
    d.mkdir()
    write_zip(d / "Jam.zip", {
        "everest.yaml": "- Name: Jam\n",
        "Maps/Jam/0-Gyms/1-Beginner.bin": b"",
        "Maps/Jam/0-Lobbies/1-Beginner.bin": b"",
        "Maps/Jam/1-Beginner/alice.bin": b"",
        "Maps/Jam/1-Beginner/bob.bin": b"",
        "Dialog/English.txt": JAM_DIALOG,
    })
    return d, jam_save(tmp_path / "1.celeste")


def test_title_on_the_line_under_its_key(jam):
    mods = scan_mods(jam[0])
    assert mods.title("Jam/1-Beginner") == "Jam - Beginner"
    assert mods.title("Jam/1-Beginner/alice") == "Sunken Garden"   # not the author's name, not the next key
    assert mods.title("Jam/1-Beginner/alice_author") == "by alice"
    assert mods.title("Jam/1-Beginner/bob") == "Quiet Cliffs"      # same-line values still work; first wins
    assert mods.title("Jam/0-Lobbies/1-Beginner") == "Beginner Lobby"


def test_parse_dialog_continued_lines_and_encodings():
    d = parse_dialog(b"a=\n  one\n  two\n# note\nb= x\nnot a key = no\nc d= e\n")
    assert d == {"a": "one\ntwo", "b": "x\nnot a key = no\nc d= e"}  # a key is one word, as in the game
    assert parse_dialog("﻿K= v\n".encode("utf-8")) == {"k": "v"}
    assert parse_dialog("K=\n  été\n".encode("utf-16")) == {"k": "été"}  # UTF-16 with BOM


def test_cache_from_an_older_version_is_read_again(jam):
    class OldCache:  # what store.ModCache returns for a zip cached before READ_VERSION 2
        def get(self, path, size, mtime_ns):
            return True, {"id": "Jam", "source": "Jam", "bins": ["Jam/1-Beginner/alice"], "dialog": {}}
        def put(self, *args):
            self.put_args = args
        def keep_only(self, paths):
            pass
    cache = OldCache()
    mods = scan_mods(jam[0], cache)
    assert mods.title("Jam/1-Beginner/alice") == "Sunken Garden"
    assert cache.put_args[3]["version"] == 2
