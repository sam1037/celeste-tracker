import json
from datetime import datetime, timezone

import pytest

from celeste_tracker.cli import main
from celeste_tracker.store import Store

from conftest import SLOTS


@pytest.fixture
def run(tmp_path, capsys):
    """Run the CLI with a scratch config (the store and the mod list cache sit next to it), offline, so tests
    never touch the user's real files or the network."""
    def _run(*args):
        main(["--config", str(tmp_path / "config.toml"), "--offline", *args])
        return capsys.readouterr().out
    return _run


def line_of(out, start):
    return next(l for l in out.splitlines() if l.startswith(start))


def test_overview_one_slot(run, mods_dir):
    out = run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir))
    line = line_of(out, "The Forest")  # the mod, named after its only chapter
    assert "2/3" in line and "0/1" in line and "in progress" in line
    assert line.endswith("(room c-02) *")
    assert "Resume: The Forest (Test/Sides/Forest, C-side), room c-02" in out
    assert "The Forest (Test/Sides/Forest)  done: A B; C: in progress" in out
    assert "Gone/Old [not loaded]" in out and "0/1?" in out
    assert "Collab D Side" not in out  # not started: hidden


def test_all_slots_combined_is_the_default(run, mods_dir):
    out = run("--saves", str(SLOTS), "--mods", str(mods_dir))
    assert "(2 slots; each mod from its furthest slot)" in out
    collab = line_of(out, "Collab ")
    assert "2/4" in collab and "1 (+1)" in collab  # slot 1 (Lobby, M1) is furthest; also played in slot 2
    assert "Slot 1: Resume:" in out
    one = run("--saves", str(SLOTS), "--mods", str(mods_dir), "--slot", "2")
    assert "1/4" in line_of(one, "Collab ")


def test_collab_shows_its_level_sets(run, tmp_path):
    mods = tmp_path / "Mods2"
    mods.mkdir()
    from conftest import write_zip
    write_zip(mods / "Big.zip", {"Maps/Big/1-Easy/m1.bin": b"", "Maps/Big/2-Hard/m2.bin": b"",
                                 "Dialog/English.txt": "Big_1_Easy= Easy\nBig_2_Hard= Hard\n"})
    save = tmp_path / "1.celeste"
    save.write_text('''<SaveData><LevelSets><LevelSetStats Name="Big/1-Easy"><Areas><AreaStats SID="Big/1-Easy/m1">
        <Modes><AreaModeStats Completed="true" HeartGem="true" Deaths="1" TimePlayed="5"><Checkpoints />
        </AreaModeStats></Modes></AreaStats></Areas></LevelSetStats></LevelSets></SaveData>''')
    out = run("--file", str(save), "--mods", str(mods))
    lines = out.splitlines()
    i = lines.index(line_of(out, "Big "))
    assert "1/2" in lines[i]
    assert lines[i + 1].startswith("  ├ Easy") and "complete" in lines[i + 1]
    assert lines[i + 2].startswith("  └ Hard") and "not started" in lines[i + 2]
    detail = run("--file", str(save), "--mods", str(mods), "--set", "Hard")  # a level set: just that one
    assert "Hard (Big/2-Hard): sides 0/1, not started" in detail and "Easy" not in detail
    assert "Sides 0/1 done, chapters 0/1 done (0 in progress, 1 not opened)" in detail  # the tier's own totals


def test_set_view_of_a_one_chapter_mod_lists_sides(run, mods_dir):
    out = run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir), "--set", "Sides Mod")
    assert out.startswith("The Forest  (mod ID: Sides Mod)")
    assert "Sides 2/3 done, chapters 0/1 done (1 in progress, 0 not opened)" in out
    assert "Chapter" not in out  # one chapter: straight to its sides
    assert any(l.startswith("C ") and "in progress" in l and 'c-01 "Deep Woods"' in l for l in out.splitlines())


def test_set_view_names_the_slot_shown_and_the_others(run, mods_dir):
    out = run("--saves", str(SLOTS), "--mods", str(mods_dir), "--set", "Collab")
    assert "Shown: slot 1, the furthest; also played in slot 2 (1/4)" in out


def test_json(run, mods_dir):
    data = json.loads(run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir), "--json", "-"))
    assert data["schema"] == 2
    assert [s["key"] for s in data["slots"]] == ["1"]
    forest = next(m for m in data["mods"] if m["id"] == "Sides Mod")["sets"][0]["chapters"][0]
    assert forest["sides"]["C"]["progress"]["1"]["status"] == "in progress"
    assert forest["sides"]["C"]["progress"]["all"]["status"] == "in progress"
    assert forest["sides"]["A"]["progress"]["1"]["checkpoints"] == [{"room": "b-01", "title": ""}]


def test_note(run, tmp_path):
    out = run("--file", str(SLOTS / "1.celeste"), "--note", "Forest", "stopped at C")
    assert "Saved note for Test/Sides/Forest" in out
    assert Store(tmp_path / "tracker.db").user_fields() == {"Test/Sides/Forest": {"note": "stopped at C"}}
    assert "<- stopped at C" in run("--file", str(SLOTS / "1.celeste"))


def test_note_on_a_name_shared_by_a_mod_and_its_chapter_goes_to_the_mod(run, tmp_path, mods_dir):
    out = run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir), "--note", "The Forest", "great map")
    assert "Saved note for Sides Mod" in out
    assert "note: great map" in run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir))


def test_save_config_then_run_without_flags(run, tmp_path, mods_dir):
    run("--saves", str(SLOTS), "--mods", str(mods_dir), "--save-config")
    assert f'saves = "{SLOTS.resolve()}"' in (tmp_path / "config.toml").read_text()
    out = run()  # Saves and Mods come from the config
    assert "(2 slots; each mod from its furthest slot)" in out and "The Forest" in out
    assert "The Forest" not in run("--no-mods")


def test_cached_gamebanana_titles_are_used(run, tmp_path, mods_dir):
    (tmp_path / "moddb.json").write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "mods": {"Sides Mod": {"title": "Forest Journey", "author": "x"}}}))
    out = run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir))
    assert line_of(out, "Forest Journey") and "1 named from GameBanana" in out


def test_unreadable_slot_is_skipped(run, tmp_path, capsys):
    saves = tmp_path / "Saves"
    saves.mkdir()
    (saves / "1.celeste").write_bytes((SLOTS / "1.celeste").read_bytes())
    (saves / "2.celeste").write_text("<SaveData><Areas>")  # cut off mid-write
    main(["--config", str(tmp_path / "c.toml"), "--offline", "--saves", str(saves)])
    out, err = capsys.readouterr()
    assert "Save:" in out and "skipping" in err


def test_user_fields_show_in_the_overview_and_json(run, mods_dir):
    args = ("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir))
    assert "Saved rating for Sides Mod: 4/5" in run(*args, "--rate", "The Forest", "4")
    run(*args, "--difficulty", "Sides Mod", "GM+1")
    assert "Marked Collab as dropped" in run(*args, "--drop", "Collab")
    out = run(*args)
    assert "Mine" in out.splitlines()[3]
    assert "4/5 · GM+1" in line_of(out, "The Forest") and "dropped" in line_of(out, "Collab ")
    assert "Mine: 4/5 · GM+1" in run(*args, "--set", "Sides Mod")
    data = json.loads(run(*args, "--json", "-"))
    assert next(m for m in data["mods"] if m["id"] == "Sides Mod")["user"] == {"difficulty": "GM+1", "rating": 4}
    run(*args, "--undrop", "Collab")
    run(*args, "--rate", "Sides Mod", "0")
    assert "dropped" not in line_of(run(*args), "Collab ")


def test_rating_must_be_1_to_5(run, mods_dir):
    with pytest.raises(SystemExit, match="1 to 5"):
        run("--file", str(SLOTS / "1.celeste"), "--rate", "Forest", "9")


def test_rename_a_mod(run, mods_dir):
    args = ("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir))
    assert "Saved rename for Collab: My Collab" in run(*args, "--rename", "Collab", "My Collab")
    assert line_of(run(*args), "My Collab")
    data = json.loads(run(*args, "--json", "-"))
    assert next(m for m in data["mods"] if m["id"] == "Collab")["name_source"] == "renamed"
    run(*args, "--rename", "Collab", "")
    assert not any(l.startswith("My Collab") for l in run(*args).splitlines())
    with pytest.raises(SystemExit, match="No mod matches"):
        run(*args, "--rename", "Test/Collab/M1", "x")  # a chapter, not a mod


def test_import_notes(run, tmp_path):
    old = tmp_path / "celeste_notes.json"
    old.write_text(json.dumps({"Test/Sides/Forest": "from the old file"}))
    assert "Imported 1 note(s)" in run("--file", str(SLOTS / "1.celeste"), "--import-notes", str(old))
    assert "<- from the old file" in run("--file", str(SLOTS / "1.celeste"))
