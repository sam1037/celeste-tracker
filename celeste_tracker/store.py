"""The tracker's own data (doc/DESIGN.md, "Store"): one SQLite file next to the config, never in the repo.

- user_fields: what the player adds, per mod ID, level set or chapter SID: note, difficulty, rating, dropped,
  and a rename (mods only).
- mod_cache: what was read from each mod zip, keyed by path, size and mtime, so unchanged zips aren't reopened.
- meta: the schema version, and the page's own settings (which columns are shown, their widths).
The save files and the Mods folder are never written (PRD #11); only this file is.
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
FIELDS = ("note", "difficulty", "rating", "dropped", "rename")
OLD_NOTES = Path(__file__).resolve().parent.parent / "celeste_notes.json"  # before the store, notes lived here

TABLES = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS user_fields (
    key        TEXT PRIMARY KEY,   -- mod ID, level set name or chapter SID
    note       TEXT,
    difficulty TEXT,               -- free text: "Expert", "GM+1", ...
    rating     INTEGER,            -- 1 to 5
    dropped    INTEGER NOT NULL DEFAULT 0,
    rename     TEXT,               -- mods only: shown instead of the GameBanana title
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS mod_cache (
    path     TEXT PRIMARY KEY,
    size     INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    data     TEXT NOT NULL          -- JSON from mods.read_zip(), "null" for a zip without maps
);
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The UI server may run on another thread than the one that opened the store (tests, the desktop window);
        # it handles one request at a time, so the connection is never used by two threads at once.
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        # WAL with synchronous=NORMAL: commits don't wait for an fsync (100+ ms each on WSL's disk); a crash can
        # lose the last change at most, never corrupt the file.
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA synchronous = NORMAL")
        with self.db:
            self.db.executescript(TABLES)
            version = self.meta("schema")
            if version is None:
                self.set_meta("schema", str(SCHEMA))
            elif int(version) > SCHEMA:
                sys.exit(f"{self.path} was written by a newer version of celeste-tracker.")

    def close(self):
        self.db.close()

    def meta(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key, value):
        self.db.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                        "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))

    # ------------------------------------------------------------ user fields

    def user_fields(self):
        """{key: {'note', 'difficulty', 'rating', 'dropped', 'rename'}}, only the fields that are set."""
        out = {}
        for row in self.db.execute("SELECT * FROM user_fields"):
            f = {k: row[k] for k in FIELDS if row[k] not in (None, "", 0)}
            if "dropped" in f:
                f["dropped"] = True
            if f:
                out[row["key"]] = f
        return out

    def set_field(self, key, field, value):
        """Set one field; None, "" or 0 clears it. A key with nothing left is deleted."""
        if field not in FIELDS:
            raise ValueError(f"unknown field {field!r}")
        if field == "rating" and value and not 1 <= int(value) <= 5:
            raise ValueError("rating must be 1 to 5 (0 clears it)")
        if field == "dropped":
            value = 1 if value else 0
        elif value in ("", 0):
            value = None
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db:
            self.db.execute(f"INSERT INTO user_fields (key, {field}, updated_at) VALUES (?, ?, ?) "
                            f"ON CONFLICT (key) DO UPDATE SET {field} = excluded.{field}, "
                            f"updated_at = excluded.updated_at", (key, value, now))
            self.db.execute("DELETE FROM user_fields WHERE key = ? AND note IS NULL AND difficulty IS NULL "
                            "AND rating IS NULL AND dropped = 0 AND rename IS NULL", (key,))

    def import_notes(self, path):
        """Notes from a celeste_notes.json ({key: note}); notes already in the store win. Returns how many."""
        try:
            notes = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        except json.JSONDecodeError as e:
            sys.exit(f"{path} is not valid JSON ({e}).")
        have = self.user_fields()
        new = {k: v for k, v in notes.items() if v and not have.get(k, {}).get("note")}
        for k, v in new.items():
            self.set_field(k, "note", str(v))
        return len(new)

    def import_old_notes_once(self, path=OLD_NOTES):
        """The first time the store is used, bring over notes from the old JSON file (it is left in place)."""
        if self.meta("old_notes_imported"):
            return 0
        n = self.import_notes(path)
        with self.db:
            self.set_meta("old_notes_imported", str(path))
        return n

    # ------------------------------------------------------------ page settings

    def page_prefs(self):
        """The --serve page's settings (hidden columns, column widths), as the page last sent them. They live here,
        not in the browser: the desktop window forgets its localStorage, and gets a new port every run."""
        try:
            prefs = json.loads(self.meta("page_prefs") or "{}")
        except json.JSONDecodeError:
            return {}
        return prefs if isinstance(prefs, dict) else {}

    def set_page_prefs(self, prefs):
        with self.db:
            self.set_meta("page_prefs", json.dumps(prefs, separators=(",", ":")))

    # ------------------------------------------------------------ mod-scan cache

    def mod_cache(self):
        return ModCache(self.db)


class ModCache:
    """The cache interface mods.scan_mods() expects. Changes are written in one transaction by keep_only()."""

    def __init__(self, db):
        self.db = db
        self.rows = {r["path"]: (r["size"], r["mtime_ns"], r["data"]) for r in db.execute("SELECT * FROM mod_cache")}
        self.new = {}

    def get(self, path, size, mtime_ns):
        row = self.rows.get(path)
        if row and row[0] == size and row[1] == mtime_ns:
            return True, json.loads(row[2])
        return False, None

    def put(self, path, size, mtime_ns, value):
        self.new[path] = (size, mtime_ns, json.dumps(value, ensure_ascii=False))

    def keep_only(self, paths):
        """Save new entries and forget zips that are gone."""
        gone = set(self.rows) - set(paths)
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO mod_cache (path, size, mtime_ns, data) VALUES (?, ?, ?, ?)",
                                [(p, *v) for p, v in self.new.items()])
            self.db.executemany("DELETE FROM mod_cache WHERE path = ?", [(p,) for p in gone])
        self.rows.update(self.new)
        for p in gone:
            self.rows.pop(p, None)
        self.new = {}
