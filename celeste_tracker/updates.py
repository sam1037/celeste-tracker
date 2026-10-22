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


def read_cache(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data, datetime.fromisoformat(data["checked_at"])
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return None, None


class Updates:
    """What the page's /api/update shows: {current, latest, url, checked_at, error, off}. `latest` is the newer
    version's tag, or None when up to date, unknown or off."""

    def __init__(self, cache_path, enabled=True, fetch=fetch, current=__version__, now=None):
        self.cache_path, self.enabled, self.fetch, self.current = Path(cache_path), enabled, fetch, current
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        cached, _ = read_cache(self.cache_path)
        self.result = cached if enabled else None
        self.error = None

    def state(self):
        r = self.result or {}
        newer = is_newer(r.get("tag"), self.current)
        return {"current": self.current, "latest": r.get("tag") if newer else None,
                "url": r.get("url") if newer else RELEASES_PAGE, "checked_at": r.get("checked_at"),
                "error": self.error, "off": not self.enabled}

    def check(self, force=False):
        """Ask GitHub, unless the last answer is less than a day old (force: ask anyway). Returns state()."""
        if not self.enabled:
            return self.state()
        with self.lock:  # the start-up thread and a click on "Check for updates" at the same time
            _, checked_at = read_cache(self.cache_path)
            if force or checked_at is None or self.now() - checked_at >= MAX_AGE:
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

    def check_in_background(self):
        if self.enabled:
            threading.Thread(target=self.check, daemon=True).start()
