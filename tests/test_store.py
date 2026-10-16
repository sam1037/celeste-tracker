import json
import os

import pytest

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
    with pytest.raises(SystemExit, match="newer version"):
        Store(tmp_path / "t.db")


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
