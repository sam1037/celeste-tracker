import json
from datetime import datetime, timedelta, timezone

import pytest

from celeste_tracker.moddb import SEARCH_URL, UPDATE_URL, join, load_titles, parse_search, parse_update

# Trimmed copies of the two files' real structure.
UPDATE = """'   Spaced Mod':
  Version: 0.1.0
  GameBananaFileId: '111'
SonderCrispy:
  Version: 1.0.3
  LastUpdate: 1775496429
  GameBananaFileId: '1669303'
  URL: https://gamebanana.com/mmdl/1669303
NotListed:
  GameBananaFileId: '999'
"""

SEARCH = """- Author: Crispybag
  Category:
    ID: GameBanana_Mod_6801
    Name: Standalone
  Description: Small plantlife blooming is a tiny victory
  Files:
  - Description: 1.0.3 - Final Version Surely
    URL: https://gamebanana.com/mmdl/1669303
    Name: sonder_0d559.zip
    ID: GameBanana/1669303
  - ID: GameBanana/1500000
    Name: sonder_old.zip
  GameBananaType: Obsolete
  Name: Sonder
  PageURL: https://gamebanana.com/mods/666256
- Name: 'It''s Spaced'
  Author: someone
  Files:
  - ID: GameBanana/111
"""


def test_parse_update():
    assert parse_update(UPDATE) == {"   Spaced Mod": "111", "SonderCrispy": "1669303", "NotListed": "999"}


def test_parse_search_reads_only_the_entry_keys():
    s = parse_search(SEARCH)
    assert s["1669303"] == {"title": "Sonder", "author": "Crispybag"}  # not "Standalone" or the zip name
    assert s["1500000"] == {"title": "Sonder", "author": "Crispybag"}  # an older file of the same mod
    assert s["111"] == {"title": "It's Spaced", "author": "someone"}


def test_join():
    assert join(parse_update(UPDATE), parse_search(SEARCH)) == {
        "   Spaced Mod": {"title": "It's Spaced", "author": "someone"},
        "SonderCrispy": {"title": "Sonder", "author": "Crispybag"}}


NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)


def fake_fetch(url):
    return {UPDATE_URL: UPDATE, SEARCH_URL: SEARCH}[url]


def no_fetch(url):
    raise AssertionError("must not download")


def failing_fetch(url):
    raise OSError("no internet")


def write_cache(path, age, mods):
    path.write_text(json.dumps({"fetched_at": (NOW - age).isoformat(), "mods": mods}))


def test_downloads_and_caches(tmp_path):
    cache = tmp_path / "moddb.json"
    titles = load_titles(cache, fetch=fake_fetch, now=NOW)
    assert titles["SonderCrispy"]["title"] == "Sonder"
    assert json.loads(cache.read_text())["mods"] == titles


def test_fresh_cache_is_not_refreshed(tmp_path):
    cache = tmp_path / "moddb.json"
    write_cache(cache, timedelta(days=1), {"X": {"title": "Cached", "author": ""}})
    assert load_titles(cache, fetch=no_fetch, now=NOW)["X"]["title"] == "Cached"


def test_stale_cache_is_used_when_the_download_fails(tmp_path, capsys):
    cache = tmp_path / "moddb.json"
    write_cache(cache, timedelta(days=30), {"X": {"title": "Cached", "author": ""}})
    assert load_titles(cache, fetch=failing_fetch, now=NOW)["X"]["title"] == "Cached"
    assert "couldn't download" in capsys.readouterr().err


@pytest.mark.parametrize("fetch", [no_fetch, failing_fetch])
def test_no_cache_offline_or_failing_gives_no_titles(tmp_path, fetch):
    assert load_titles(tmp_path / "moddb.json", offline=fetch is no_fetch, fetch=fetch, now=NOW) == {}


def test_empty_download_keeps_the_cache(tmp_path):
    cache = tmp_path / "moddb.json"
    write_cache(cache, timedelta(days=30), {"X": {"title": "Cached", "author": ""}})
    assert load_titles(cache, fetch=lambda url: "", now=NOW)["X"]["title"] == "Cached"
    assert json.loads(cache.read_text())["mods"]["X"]["title"] == "Cached"
