"""GameBanana titles for mod IDs, from Everest's public mod database (doc/DESIGN.md, "Mod database").

Two public files are downloaded (plain GET, nothing about the player is sent):
- everest_update.yaml: mod ID (everest.yaml Name) -> GameBananaFileId
- mod_search_database.yaml: GameBanana entries with their title (Name), Author and Files (IDs)
Only the joined mod ID -> {title, author} map is kept, as moddb.json in the user data folder.
"""
import gzip
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

UPDATE_URL = "https://maddie480.ovh/celeste/everest_update.yaml"
SEARCH_URL = "https://maddie480.ovh/celeste/mod_search_database.yaml"
MAX_AGE = timedelta(days=7)
USER_AGENT = "celeste-tracker/0.1 (reads save progress locally; fetches the public mod list for titles)"


def unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)
        except ValueError:
            return v[1:-1]
    return v


def parse_update(text):
    """everest_update.yaml -> {mod ID: GameBanana file ID}. Top-level keys are mod IDs."""
    out, cur = {}, None
    for line in text.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            cur = unquote(line.rstrip()[:-1])
        elif cur:
            m = re.match(r"\s+GameBananaFileId:\s*(.+)$", line)
            if m:
                out[cur] = unquote(m[1])
    return out


def parse_search(text):
    """mod_search_database.yaml -> {GameBanana file ID: {'title', 'author'}}.

    Each entry starts with '- ' in column 0. Its own keys are indented 2 spaces (or sit on the '- ' line);
    deeper keys (Category's Name, Files' Name) belong to nested items. File IDs look like 'ID: GameBanana/123'.
    """
    out = {}
    entry, files = {}, []

    def flush():
        for f in files:
            out[f] = {"title": entry.get("Name", ""), "author": entry.get("Author", "")}

    for line in text.splitlines():
        if line.startswith("- "):
            flush()
            entry, files = {}, []
            line = "  " + line[2:]
        m = re.match(r"  (Name|Author): (.*)$", line)
        if m:
            entry[m[1]] = unquote(m[2])
            continue
        m = re.match(r"\s+(?:- )?ID: GameBanana/(\d+)\s*$", line)
        if m:
            files.append(m[1])
    flush()
    return out


def join(update, search):
    """{mod ID: {'title', 'author'}} for every mod ID whose file is listed in the search database."""
    return {mod_id: search[fid] for mod_id, fid in update.items() if fid in search and search[fid]["title"]}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
    return data.decode("utf-8", "replace")


def read_cache(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data, datetime.fromisoformat(data["fetched_at"])
    except (FileNotFoundError, ValueError, KeyError):
        return None, None


def load_titles(cache_path, offline=False, refresh=False, fetch=fetch, now=None):
    """{mod ID: {'title', 'author'}}. Uses the cache while it's fresh; otherwise downloads, unless offline.
    A failed download falls back to the old cache, or to {} (names then come from the mods' own files)."""
    now = now or datetime.now(timezone.utc)
    cached, fetched_at = read_cache(cache_path)
    fresh = cached is not None and now - fetched_at < MAX_AGE
    if offline or (fresh and not refresh):
        return cached["mods"] if cached else {}
    try:
        mods = join(parse_update(fetch(UPDATE_URL)), parse_search(fetch(SEARCH_URL)))
    except (OSError, ValueError) as e:  # URLError, timeouts and HTTP errors are OSErrors
        note = "using the cached titles" if cached else "using names from the mod files"
        print(f"Note: couldn't download the mod list for GameBanana titles ({e}); {note}.", file=sys.stderr)
        return cached["mods"] if cached else {}
    if not mods:  # a format change upstream: don't overwrite a good cache with nothing
        print("Note: the downloaded mod list had no titles; keeping the cached ones.", file=sys.stderr)
        return cached["mods"] if cached else {}
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"fetched_at": now.isoformat(timespec="seconds"), "mods": mods},
                                     ensure_ascii=False), encoding="utf-8")
    return mods
