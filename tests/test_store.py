import json
import os
import sqlite3

import pytest

from celeste_tracker import store as store_module
from celeste_tracker.mods import scan_mods
from celeste_tracker.store import Store

from conftest import write_zip


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "tracker.db")
    yield s
    s.close()


def test_fields_set_and_clear(store):
    store.set_field("Mod", "note", "hi")
    store.set_field("Mod", "rating", 4)
    store.set_field("Mod", "dropped", True)
    assert store.user_fields() == {"Mod": {"note": "hi", "rating": 4, "dropped": True}}
    store.set_field("Mod", "note", "")
    store.set_field("Mod", "rating", 0)
    store.set_field("Mod", "dropped", False)
    assert store.user_fields() == {}
    assert store.db.execute("SELECT count(*) FROM user_fields").fetchone()[0] == 0  # empty rows are deleted


def test_bad_values(store):
    with pytest.raises(ValueError):
        store.set_field("Mod", "rating", 6)
    with pytest.raises(ValueError):
        store.set_field("Mod", "colour", "red")


def test_difficulty_is_one_of_the_tiers(store):
    store.set_field("Mod", "difficulty", "Expert")
    with pytest.raises(ValueError, match="Grandmaster"):
        store.set_field("Mod", "difficulty", "GM+1")
    assert store.user_fields() == {"Mod": {"difficulty": "Expert"}}


def test_tags(store):
    assert store.set_tags("Mod", ["  For   Golden ", "tech", "TECH", ""]) == ["for golden", "tech"]
    store.set_field("Mod", "rating", 3)
    assert store.user_fields() == {"Mod": {"rating": 3, "tags": ["for golden", "tech"]}}
    assert store.set_tags("Other", ["x" * 50]) == ["x" * 30]
    with pytest.raises(ValueError, match="at most 20"):
        store.set_tags("Mod", [f"t{n}" for n in range(21)])
    store.set_tags("Mod", [])
    assert store.user_fields() == {"Mod": {"rating": 3}, "Other": {"tags": ["x" * 30]}}


def test_import_notes_keeps_existing_ones(store, tmp_path):
    store.set_field("A", "note", "newer")
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"A": "older", "B": "only here"}))
    assert store.import_notes(old) == 1
    assert store.user_fields() == {"A": {"note": "newer"}, "B": {"note": "only here"}}


def test_old_notes_are_imported_once(store, tmp_path):
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"A": "x"}))
    assert store.import_old_notes_once(old) == 1
    store.set_field("A", "note", "")
    assert store.import_old_notes_once(old) == 0  # not brought back after the user removed it


def test_reopening_keeps_data(tmp_path):
    Store(tmp_path / "t.db").set_field("Mod", "rename", "Mine")
    assert Store(tmp_path / "t.db").user_fields() == {"Mod": {"rename": "Mine"}}


def test_newer_store_is_refused(tmp_path):
    s = Store(tmp_path / "t.db")
    with s.db:
        s.set_meta("schema", "99")
    s.close()
    with pytest.raises(SystemExit, match="newer version.*releases"):
        Store(tmp_path / "t.db")


def old_store(path, monkeypatch, steps):
    """A store written at schema 1 with a note, then the code moved to schema 1 + len(steps)."""
    s = Store(path)
    s.set_field("Mod", "note", "hi")
    s.close()
    monkeypatch.setattr(store_module, "SCHEMA", 1 + len(steps))
    monkeypatch.setattr(store_module, "MIGRATIONS", {1 + i: f for i, f in enumerate(steps)})


def test_an_older_store_is_upgraded_with_a_copy_kept(tmp_path, monkeypatch):
    old_store(tmp_path / "t.db", monkeypatch, [
        lambda db: db.execute("ALTER TABLE user_fields ADD COLUMN favourite INTEGER"),
        lambda db: db.execute("UPDATE user_fields SET favourite = 1"),
    ])
    s = Store(tmp_path / "t.db")
    assert s.meta("schema") == "3" and s.user_fields() == {"Mod": {"note": "hi"}}
    assert s.db.execute("SELECT favourite FROM user_fields").fetchone()[0] == 1
    s.close()
    copy = sqlite3.connect(tmp_path / "t.db.bak-schema1")
    assert copy.execute("SELECT note FROM user_fields").fetchone()[0] == "hi"
    assert copy.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()[0] == "1"
    copy.close()
    Store(tmp_path / "t.db").close()  # opened again: nothing left to do


def test_a_failed_upgrade_changes_nothing(tmp_path, monkeypatch):
    def broken(db):
        raise sqlite3.OperationalError("bug in step 2")
    old_store(tmp_path / "t.db", monkeypatch, [
        lambda db: db.execute("ALTER TABLE user_fields ADD COLUMN favourite INTEGER"), broken])
    with pytest.raises(sqlite3.OperationalError):
        Store(tmp_path / "t.db")
    db = sqlite3.connect(tmp_path / "t.db")
    assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()[0] == "1"
    assert "favourite" not in [r[1] for r in db.execute("PRAGMA table_info(user_fields)")]  # the ALTER was undone
    db.close()


def backups(tmp_path):
    return sorted(p.name for p in (tmp_path / "backups").glob("*"))


def test_a_backup_a_day_without_the_mod_cache(tmp_path, mods_dir):
    s = Store(tmp_path / "t.db")
    assert not (tmp_path / "backups").exists()  # nothing of the player's yet
    scan_mods(mods_dir, s.mod_cache())
    s.set_field("Mod", "rating", 4)
    s.set_tags("Mod", ["golden"])
    s.backup_daily(today="2026-10-01")
    s.set_field("Mod", "rating", 5)
    s.backup_daily(today="2026-10-01")  # one a day: not replaced
    assert backups(tmp_path) == ["t-2026-10-01.db"]
    copy = Store(tmp_path / "backups" / "t-2026-10-01.db")
    assert copy.user_fields() == {"Mod": {"rating": 4, "tags": ["golden"]}}
    assert copy.db.execute("SELECT count(*) FROM mod_cache").fetchone()[0] == 0
    copy.close()


def test_backups_keep_the_last_seven_days(tmp_path):
    s = Store(tmp_path / "t.db")
    s.set_field("Mod", "note", "hi")
    for day in range(1, 11):
        s.backup_daily(today=f"2026-10-{day:02}")
    assert backups(tmp_path) == [f"t-2026-10-{d:02}.db" for d in range(4, 11)]


def test_a_failed_backup_doesnt_stop_the_tracker(tmp_path, capsys):
    s = Store(tmp_path / "t.db")
    s.set_field("Mod", "note", "hi")
    (tmp_path / "backups").write_text("a file where the folder should be")
    s.backup_daily(today="2026-10-01")
    assert "couldn't back up" in capsys.readouterr().err


def test_mod_scan_cache(store, mods_dir, monkeypatch):
    first = scan_mods(mods_dir, store.mod_cache())
    import celeste_tracker.mods as mods_module
    real_read_zip = mods_module.read_zip
    monkeypatch.setattr(mods_module, "read_zip", lambda p: pytest.fail(f"re-read {p.name}"))
    second = scan_mods(mods_dir, store.mod_cache())  # nothing changed: nothing is opened
    assert (second.maps, second.dialog, second.owner) == (first.maps, first.dialog, first.owner)

    # A changed zip is read again; a removed one is forgotten.
    reread = []
    monkeypatch.setattr(mods_module, "read_zip", lambda p: reread.append(p.name) or real_read_zip(p))
    write_zip(mods_dir / "Collab.zip", {"Maps/Test/Collab/Lobby.bin": b"", "Maps/Test/Collab/New.bin": b""})
    st = (mods_dir / "Collab.zip").stat()
    os.utime(mods_dir / "Collab.zip", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    (mods_dir / "AddOn.zip").unlink()
    third = scan_mods(mods_dir, store.mod_cache())
    assert reread == ["Collab.zip"]
    assert set(third.maps["Test/Collab"]) == {"Test/Collab/Lobby", "Test/Collab/New"}
    paths = [r[0] for r in store.db.execute("SELECT path FROM mod_cache")]
    assert not any(p.endswith("AddOn.zip") for p in paths)
