"""Is there a newer version? (docs/features/app-updates.md)

Asks GitHub for the latest release of the project (a plain GET, nothing about the player is sent), at most once a
day: the answer is kept as update.json in the user data folder. Off with --offline or `check_updates = false` in
the config. Any error is quiet: no network is normal, and the page then just doesn't show a notice.
"""
import json
import re
import sys
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__

REPO = "sam1037/celeste-tracker"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
MAX_AGE = timedelta(days=1)
USER_AGENT = f"celeste-tracker/{__version__} (checks for a newer release)"


def parse_version(tag):
    """'v0.10.2' or '0.10.2' -> (0, 10, 2); None for anything else (pre-releases like 'v0.3.0-rc1' included)."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(tag).strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(tag, current=__version__):
    latest, now = parse_version(tag), parse_version(current)
    return bool(latest and now and latest > now)


def fetch(url=LATEST_URL, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def checked_at(result):
    """When a cached answer was fetched, as an aware datetime; None if it's missing or unreadable (a hand-edited
    time without a UTC offset included: it couldn't be compared with now)."""
    try:
        t = datetime.fromisoformat(result["checked_at"])
    except (ValueError, KeyError, TypeError):
        return None
    return t if t.tzinfo else None


def read_cache(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and checked_at(data) else None


class Updates:
    """What the page's /api/about shows: {current, latest, url, checked_at, checking, error, off}. `latest` is the
    newer version's tag, or None when up to date, unknown or off. One per process."""

    def __init__(self, cache_path, enabled=True, fetch=fetch, current=__version__, now=None):
        self.cache_path, self.enabled, self.fetch, self.current = Path(cache_path), enabled, fetch, current
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        self.result = read_cache(self.cache_path) if enabled else None
        self.error = None
        self.checking = False

    @classmethod
    def for_config(cls, cfg_file, cfg, offline):
        """The check for --serve and the desktop app: off with --offline or `check_updates = false`."""
        return cls(Path(cfg_file).parent / "update.json", enabled=not offline and cfg.get("check_updates", True) is not False)

    def state(self):
        r = self.result or {}
        newer = is_newer(r.get("tag"), self.current)
        return {"current": self.current, "latest": r.get("tag") if newer else None,
                "url": r.get("url") if newer else RELEASES_PAGE, "checked_at": r.get("checked_at"),
                "checking": self.checking, "error": self.error, "off": not self.enabled}

    def check(self, force=False):
        """Ask GitHub, unless the last answer is less than a day old (force: ask anyway). Returns state()."""
        if not self.enabled:
            return self.state()
        with self.lock:  # the start-up thread and a click on "Check for updates" at the same time
            last = checked_at(self.result or {})
            if force or last is None or self.now() - last >= MAX_AGE:
                try:
                    release = self.fetch()
                    tag, url = release["tag_name"], release.get("html_url") or RELEASES_PAGE
                    if not isinstance(tag, str) or not str(url).startswith("https://github.com/"):
                        raise ValueError("unexpected answer from GitHub")
                except (OSError, ValueError, KeyError, TypeError) as e:  # URLError and HTTP errors are OSErrors
                    self.error = "Couldn't reach GitHub"
                    print(f"Note: couldn't check for a newer version ({e}).", file=sys.stderr)
                    return self.state()
                self.result = {"tag": tag, "url": url, "checked_at": self.now().isoformat(timespec="seconds")}
                self.error = None
                try:
                    self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                    self.cache_path.write_text(json.dumps(self.result), encoding="utf-8")
                except OSError:
                    pass
        return self.state()

    def check_in_background(self, force=False):
        """The same on a thread, so the server never waits for GitHub; state()["checking"] is true until it's done.
        Returns state()."""
        if self.enabled and not self.checking:
            self.checking = True

            def run():
                try:
                    self.check(force)
                finally:
                    self.checking = False
            threading.Thread(target=run, daemon=True).start()
        return self.state()
