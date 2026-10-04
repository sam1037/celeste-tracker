import json

import pytest

from celeste_tracker.cli import main

from conftest import SLOTS


@pytest.fixture
def run(tmp_path, capsys):
    """Run the CLI with a scratch config and notes file, so tests never touch the user's real ones."""
    def _run(*args):
        main(["--config", str(tmp_path / "config.toml"), "--notes", str(tmp_path / "notes.json"), *args])
        return capsys.readouterr().out
    return _run


def test_overview(run, mods_dir):
    out = run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir))
    line = next(l for l in out.splitlines() if l.startswith("Side Set (Test/Sides)"))
    assert "Sides Mod" in line and "2/3" in line and "0/1" in line and "in progress" in line
    assert line.endswith("(room c-02) *")
    assert "Resume: The Forest (Test/Sides/Forest, C-side), room c-02" in out
    assert "The Forest (Test/Sides/Forest)  done: A B; C: in progress" in out
    assert "Gone/Old [not loaded]" in out and "0/1?" in out


def test_set_view(run, mods_dir):
    out = run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir), "--set", "Sides Mod")
    assert "Sides 2/3 done, maps 0/1 done (1 in progress, 0 not opened)" in out
    assert any(l.split()[:1] == ["C"] and "in progress" in l and 'c-01 "Deep Woods"' in l for l in out.splitlines())


def test_json(run, mods_dir):
    data = json.loads(run("--file", str(SLOTS / "1.celeste"), "--mods", str(mods_dir), "--json", "-"))
    assert data["schema"] == 1
    sets = {s["name"]: s for s in data["slots"][0]["sets"]}
    forest = sets["Test/Sides"]["maps"][0]
    assert forest["sides"]["C"]["status"] == "in progress"
    assert forest["sides"]["A"]["checkpoints"] == [{"room": "b-01", "title": ""}]


def test_all_slots(run, mods_dir):
    out = run("--all", "--saves", str(SLOTS), "--mods", str(mods_dir))
    assert "(2 slots)" in out
    collab = [l for l in out.splitlines() if "(Test/Collab)" in l or l.split()[1:2] == ["Test/Collab"]]
    assert [l.split()[0] for l in collab] == ["1", "2"]  # the same set, once per slot
    assert "Slot 1: Resume:" in out


def test_note(run, tmp_path):
    out = run("--file", str(SLOTS / "1.celeste"), "--note", "Forest", "stopped at C")
    assert "Saved note for Test/Sides/Forest" in out
    assert json.loads((tmp_path / "notes.json").read_text()) == {"Test/Sides/Forest": "stopped at C"}
    assert "<- stopped at C" in run("--file", str(SLOTS / "1.celeste"))


def test_save_config_then_run_without_flags(run, tmp_path, mods_dir):
    run("--saves", str(SLOTS), "--mods", str(mods_dir), "--save-config")
    assert f'saves = "{SLOTS.resolve()}"' in (tmp_path / "config.toml").read_text()
    out = run("--all")  # Saves and Mods come from the config
    assert "(2 slots)" in out and "Sides Mod" in out
    assert "Sides Mod" not in run("--all", "--no-mods")


def test_unreadable_slot_is_skipped_in_all(run, tmp_path, capsys):
    saves = tmp_path / "Saves"
    saves.mkdir()
    (saves / "1.celeste").write_bytes((SLOTS / "1.celeste").read_bytes())
    (saves / "2.celeste").write_text("<SaveData><Areas>")  # cut off mid-write
    main(["--config", str(tmp_path / "c.toml"), "--notes", str(tmp_path / "n.json"), "--all", "--saves", str(saves)])
    out, err = capsys.readouterr()
    assert "(1 slots)" in out and "skipping" in err
