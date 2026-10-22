# Plan: tell players about new versions, and keep their data across updates

Requested by the user (2026-10-22; TODO.md "update notice" and "Keep the player's data across app updates"). Built on branch `app-updates` the same day (steps 2, 3, 5, 6); what changed from the plan is under "As built". Left: step 1 and the desktop check in step 4 (TODO.md).

## The problem

- Releases are GitHub tags (`vX.Y.Z`, NOTES.md "Release"). Nothing in the app says a new one is out, so players stay on the version they first downloaded.
- The user's worry: a new download loses notes, ratings, difficulty, tags and names unless the player copies the old `_internal` folder over.

## What the code does today

- The player's data is **not** in `_internal`. `tracker.db` and `config.toml` live in `paths.data_dir()`: `%APPDATA%\celeste-tracker` on Windows, `~/Library/Application Support/celeste-tracker` on macOS. `_internal` only holds Python, the libraries and the page files. So replacing the app folder (or the `.app`) should keep everything, but no real update (v0.1.0 to v0.2.0) has been tried yet. Step 1 checks this before anything is built on it.
- The app doesn't know its own version: `pyproject.toml` has `version = "0.2.0"`, and the frozen build doesn't ship it.
- `store.py` refuses a `tracker.db` from a newer schema, and has no step that upgrades an older one.

## Design

### Version

- `celeste_tracker/__init__.py` gets `__version__ = "0.2.0"`; a test checks it equals `pyproject.toml`'s, so a release bump can't miss it. The release workflow also checks the tag equals `v` + `__version__` before building.
- Shown in `--version` (CLI), in the page's help panel ("Celeste Tracker v0.2.0"), and in `/api/status`.

### Update check

- `celeste_tracker/updates.py`: `GET https://api.github.com/repos/sam1037/celeste-tracker/releases/latest` (standard library `urllib`, 5 s timeout, no token: 60 requests/hour per IP is plenty). Reads `tag_name`, `html_url`, and the asset URL for this OS.
- At most once a day: the result and its time go in the store's `meta` table. `--offline` skips it; any error is silent (no network is normal).
- Config `check_updates = false` turns it off, since it contacts GitHub. Said in the README.
- Compares versions as tuples of ints (`0.10.0 > 0.9.0`); pre-release tags are ignored.
- Server: `GET /api/update` → `{current, latest, url}` (`latest` is null when up to date or unknown). The check runs on a background thread at start, so the page never waits for it.

### Page

- When `latest` is newer: a small, dismissible bar at the top, "Celeste Tracker v0.3.0 is out. Download · What's new". Dismissing hides it until the next version (the dismissed tag goes in `/api/prefs`).
- The help panel shows the current version and a **Check for updates** button (forces a check, ignoring the day limit), with the result next to it ("Up to date" / the same link / "Couldn't reach GitHub").
- Links open in the player's browser, not in the window: in the desktop app the page asks `desktop.py` to call `webbrowser.open` (pywebview would otherwise navigate the window). The `--serve` page uses `target="_blank"`.

### Upgrading

Recommended for now: **the notice links to the release page; the player downloads the zip and replaces the old folder** (Windows) or the `.app` (macOS). Their data stays in the data folder. The release notes and README say this in one line: "Replace the old folder; your notes and ratings are kept."

One-click update inside the app (later, if players ask): download the zip into the data folder, unzip next to the app, quit, and let a small helper (a `.bat`/PowerShell script on Windows, a shell script on macOS) swap the folders and restart, because a running exe can't overwrite itself. Costs: two OS-specific paths to test on real machines, antivirus suspicion on Windows, and on macOS the unsigned app gets quarantined again by every download. Not worth it before signing (DESIGN.md "Build").

### Keeping the data safe across schema changes

- `store.py` gets a migration step: `SCHEMA` goes to N, and opening a store at N-1 runs the upgrade in one transaction.
- Before a migration, copy `tracker.db` to `tracker.db.bak-v<old schema>` next to it.
- A newer store opened by an older app keeps today's message, plus "download the latest version" and the link.

## Tests

- `__version__` equals `pyproject.toml`; version comparison (`0.10.0`, `v` prefix, pre-releases).
- `updates.py` with a fake response (never the network): newer, same, error, malformed JSON, the once-a-day cache, `--offline` and `check_updates = false` skip it.
- `/api/update` on the fixtures; the bar and the help panel button with playwright-cli (a fake `latest`).
- Store: a schema N-1 fixture store upgrades, and the backup file is written.
- By hand: install v0.2.0 on Windows and macOS, add notes and ratings, replace it with the new build, check they're all there.

## Build order

1. By hand: the v0.1.0 → v0.2.0 update on Windows (and macOS), to confirm the data survives a folder swap. If it doesn't, find out why before anything else.
2. `__version__`, `--version`, the version in the help panel, the workflow tag check.
3. `updates.py`, `/api/update`, the bar and the Check for updates button.
4. Desktop: open links in the browser; Windows build.
5. Store migration and backup (when the first schema change comes, or now with a test-only schema).
6. README ("Updating"), NOTES.md, TODO.md (move to Done).

## As built (2026-10-22)

- The endpoint is `GET /api/about`, and it also gives the data folder, which the help panel shows; `POST /api/about/check` asks now, on a thread, and the page polls while `checking` is true (also at load, so it picks up the start-up check). `/api/status` stays the save-change counter.
- One `Updates` per process (`Updates.for_config`); a cached time without a UTC offset counts as no cache.
- The daily backup copies only `meta`, `user_fields` and `user_tags` into a fresh file (ATTACH), not the whole store; the pre-upgrade copy is a full `VACUUM INTO`, and if it fails the upgrade stops with a message.
- The day's answer goes in `update.json` next to the config, not the store's `meta`: the check runs on its own thread, and the store's connection stays on the server's.
- The notice is a small link in the top bar, "Version 0.3.0 is out", with a ✕; no "What's new" link (the release page has the notes). Shorter than planned so it fits on a phone next to Refresh and ?.
- Links: nothing to add in `desktop.py`. pywebview already sends `target="_blank"` links to the browser (`OPEN_EXTERNAL_LINKS_IN_BROWSER`, on by default); still to check in a Windows build.
- The asset URL per OS isn't read: the link goes to the release page.
- The pre-upgrade copy is `tracker.db.bak-schema<n>`. Added: a daily backup of the player's fields in `backups/` (last 7 days, without the mod cache), and the README says how to restore one.
- `--offline` also turns the check off in the desktop app.

## Open questions

- Also show the bar in the CLI (one line after the output)? Recommended: no, the CLI is for the author and power users.
- Should the bar say what's new (the release body), or just link to it? Recommended: link only.
