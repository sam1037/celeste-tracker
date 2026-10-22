import json
import threading
import time
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from celeste_tracker import __version__
from celeste_tracker.updates import RELEASES_PAGE, Updates, is_newer, parse_version

T0 = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def release(tag="v0.3.0"):
    return {"tag_name": tag, "html_url": f"https://github.com/sam1037/celeste-tracker/releases/tag/{tag}"}


class Fake:
    """GitHub's answer, counting the calls."""

    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def __call__(self):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_version_matches_pyproject():
    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == pyproject["project"]["version"]


def test_versions_compare_as_numbers():
    assert parse_version("v0.10.2") == (0, 10, 2) == parse_version("0.10.2")
    assert parse_version("v0.3.0-rc1") is None and parse_version("latest") is None and parse_version(None) is None
    assert is_newer("v0.10.0", "0.9.0")
    assert not is_newer("v0.2.0", "0.2.0") and not is_newer("v0.1.9", "0.2.0")
    assert not is_newer("v0.3.0-rc1", "0.2.0")  # pre-releases are ignored


def test_a_newer_release_is_shown(tmp_path):
    up = Updates(tmp_path / "update.json", fetch=Fake(release()), current="0.2.0", now=lambda: T0)
    s = up.check()
    assert s["latest"] == "v0.3.0" and s["url"].endswith("/tag/v0.3.0") and s["current"] == "0.2.0"
    assert s["error"] is None and not s["off"]


def test_up_to_date(tmp_path):
    s = Updates(tmp_path / "u.json", fetch=Fake(release("v0.2.0")), current="0.2.0", now=lambda: T0).check()
    assert s["latest"] is None and s["url"] == RELEASES_PAGE and s["checked_at"]


def test_asks_at_most_once_a_day(tmp_path):
    fake, now = Fake(release()), [T0]
    up = Updates(tmp_path / "u.json", fetch=fake, current="0.2.0", now=lambda: now[0])
    up.check()
    now[0] = T0 + timedelta(hours=23)
    up.check()
    assert fake.calls == 1
    up.check(force=True)  # "Check for updates" on the page
    assert fake.calls == 2
    now[0] = T0 + timedelta(days=2)
    up.check()
    assert fake.calls == 3


def test_the_answer_is_kept_for_the_next_start(tmp_path):
    Updates(tmp_path / "u.json", fetch=Fake(release()), current="0.2.0", now=lambda: T0).check()
    fake = Fake(AssertionError("asked again"))
    up = Updates(tmp_path / "u.json", fetch=fake, current="0.2.0", now=lambda: T0 + timedelta(hours=1))
    assert up.state()["latest"] == "v0.3.0"  # shown before any check
    assert up.check()["latest"] == "v0.3.0" and fake.calls == 0
    # After updating, the same answer is no longer news.
    assert Updates(tmp_path / "u.json", fetch=fake, current="0.3.0", now=lambda: T0).state()["latest"] is None


def test_errors_are_quiet(tmp_path):
    bad = (OSError("no network"), {"message": "rate limited"}, ["x"],
           {"tag_name": "v9.0.0", "html_url": "https://evil.example/"})
    for answer in bad:
        s = Updates(tmp_path / "u.json", fetch=Fake(answer), current="0.2.0", now=lambda: T0).check()
        assert s["latest"] is None and s["error"] == "Couldn't reach GitHub"
    assert not (tmp_path / "u.json").exists()
    (tmp_path / "u.json").write_text("not json")
    assert Updates(tmp_path / "u.json", fetch=Fake(release()), current="0.2.0", now=lambda: T0).check()["latest"] == "v0.3.0"


def test_a_time_without_a_utc_offset_is_ignored(tmp_path):
    (tmp_path / "u.json").write_text(json.dumps({"tag": "v0.3.0", "url": RELEASES_PAGE, "checked_at": "2026-10-22T10:00:00"}))
    fake = Fake(release("v0.4.0"))
    up = Updates(tmp_path / "u.json", fetch=fake, current="0.2.0", now=lambda: T0)
    assert up.state()["latest"] is None  # unreadable: as if there were no cache
    assert up.check()["latest"] == "v0.4.0" and fake.calls == 1


def test_an_unwritable_cache_still_asks_once_a_day(tmp_path):
    (tmp_path / "u.json").mkdir()  # can't be written
    fake = Fake(release())
    up = Updates(tmp_path / "u.json", fetch=fake, current="0.2.0", now=lambda: T0)
    up.check()
    up.check()
    assert fake.calls == 1 and up.state()["latest"] == "v0.3.0"


def test_check_in_background(tmp_path):
    started, go = threading.Event(), threading.Event()

    def slow():
        started.set()
        go.wait(5)
        return release()
    up = Updates(tmp_path / "u.json", fetch=slow, current="0.2.0", now=lambda: T0)
    assert up.check_in_background()["checking"]
    started.wait(5)
    assert up.check_in_background()["checking"]  # already running: not a second one
    go.set()
    for _ in range(100):
        if not up.state()["checking"]:
            break
        time.sleep(0.01)
    assert up.state()["latest"] == "v0.3.0" and not up.state()["checking"]


def test_for_config(tmp_path):
    cfg = tmp_path / "c.toml"
    assert Updates.for_config(cfg, {}, offline=False).enabled
    assert not Updates.for_config(cfg, {}, offline=True).enabled
    assert not Updates.for_config(cfg, {"check_updates": False}, offline=False).enabled
    assert Updates.for_config(cfg, {}, offline=False).cache_path == tmp_path / "update.json"


def test_off_never_asks(tmp_path):
    (tmp_path / "u.json").write_text(json.dumps({"tag": "v0.3.0", "url": RELEASES_PAGE, "checked_at": T0.isoformat()}))
    fake = Fake(release())
    up = Updates(tmp_path / "u.json", enabled=False, fetch=fake, current="0.2.0")
    up.check_in_background()
    s = up.check(force=True)
    assert fake.calls == 0 and s["off"] and s["latest"] is None
