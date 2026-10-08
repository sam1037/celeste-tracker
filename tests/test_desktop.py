"""Finding the Celeste folder (paths.py) and the desktop app's helpers, without opening a window."""
import json
import shutil
import sys
import urllib.request

from celeste_tracker import desktop, paths
from celeste_tracker.paths import (find_mods_dir, find_saves_dir, load_config, olympus_installs, saves_in,
                                   steam_libraries)

from conftest import SLOTS


def celeste(tmp_path, name="Celeste", slots=("1.celeste",), mods=True):
    """A made-up Celeste folder with Saves (and Mods)."""
    d = tmp_path / name
    (d / "Saves").mkdir(parents=True)
    for n in slots:
        shutil.copy(SLOTS / n, d / "Saves" / n)
    (d / "Saves" / "settings.celeste").write_text("<Settings />")
    if mods:
        (d / "Mods").mkdir()
    return d


def test_olympus_installs(tmp_path):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"installs": [{"type": "steam", "path": "D:\\Games\\Celeste", "name": "Steam"},
                                          {"name": "no path"}, "junk"]}))
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert olympus_installs([f, broken, tmp_path / "missing.json"]) == [paths.Path("D:\\Games\\Celeste")]


def test_steam_libraries(tmp_path):
    (tmp_path / "steamapps").mkdir()
    (tmp_path / "steamapps/libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n\t}\n'
        '\t"1"\n\t{\n\t\t"path"\t\t"E:\\\\SteamLibrary"\n\t\t"apps"\n\t\t{\n\t\t\t"504230"\t\t"1"\n\t\t}\n\t}\n}\n')
    libs = steam_libraries(tmp_path)
    assert libs == [tmp_path, paths.Path("C:\\Program Files (x86)\\Steam"), paths.Path("E:\\SteamLibrary")]
    assert steam_libraries(tmp_path / "nowhere") == [tmp_path / "nowhere"]


def test_saves_in(tmp_path):
    d = celeste(tmp_path)
    assert saves_in(d) == d / "Saves"
    assert saves_in(d / "Saves") == d / "Saves"
    assert saves_in(tmp_path / "empty") is None
    app = tmp_path / "Celeste.app/Contents/Resources/Saves"  # macOS
    app.mkdir(parents=True)
    assert saves_in(tmp_path / "Celeste.app") == app


def test_find_saves_dir_prefers_one_with_slots(tmp_path):
    empty = celeste(tmp_path, "Old", slots=())
    full = celeste(tmp_path, "New")
    assert find_saves_dir(candidates=[tmp_path / "missing", empty / "Saves", full / "Saves"]) == full / "Saves"
    assert find_saves_dir(candidates=[empty / "Saves"]) == empty / "Saves"
    assert find_saves_dir(candidates=[tmp_path / "missing"]) is None
    assert find_saves_dir("given", candidates=[]) == paths.Path("given")


def test_find_mods_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "celeste_dirs", lambda: [])
    d = celeste(tmp_path)
    assert find_mods_dir(d / "Saves") == d / "Mods"
    assert find_mods_dir(d / "Saves", "auto") == d / "Mods"
    assert find_mods_dir(d / "Saves", "/elsewhere") == paths.Path("/elsewhere")
    bare = celeste(tmp_path, "Vanilla", mods=False)
    assert find_mods_dir(bare / "Saves") is None
    monkeypatch.setattr(paths, "celeste_dirs", lambda: [d])  # Saves in the user folder, Mods in the game folder
    assert find_mods_dir(bare / "Saves") == d / "Mods"


def test_checked_saves(tmp_path):
    d = celeste(tmp_path)
    assert desktop.checked_saves(d) == (d / "Saves", None)
    saves, problem = desktop.checked_saves(tmp_path / "nothing")
    assert saves is None and "no Saves folder" in problem
    saves, problem = desktop.checked_saves(celeste(tmp_path, "Fresh", slots=()))
    assert saves is None and "no save files" in problem


def test_remember_keeps_other_settings(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('mods = "auto"\n')
    desktop.remember(cfg, tmp_path / "Celeste" / "Saves")
    assert load_config(cfg) == {"mods": "auto", "saves": str(tmp_path / "Celeste" / "Saves")}


def test_start_server_serves_the_page(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "celeste_dirs", lambda: [])
    d = celeste(tmp_path, slots=("1.celeste", "2.celeste"))
    server, url = desktop.start_server(tmp_path / "cfg" / "c.toml", d / "Saves", offline=True)
    try:
        port = server.server_address[1]
        assert url == f"http://localhost:{port}/"
        with urllib.request.urlopen(url + "api/library", timeout=10) as r:
            data = json.load(r)
        assert [s["number"] for s in data["slots"]] == [1, 2]
        assert (tmp_path / "cfg" / "tracker.db").exists()  # the store sits next to the given config
    finally:
        server.shutdown()
        server.server_close()
        server.RequestHandlerClass.app.store.close()


def test_log_to_file_without_console(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop.log_to_file(tmp_path)
    print("Note: hello", file=sys.stderr)
    sys.stderr.close()
    assert (tmp_path / "desktop.log").read_text(encoding="utf-8") == "Note: hello\n"
