# Celeste mod progress tracker: design

How the tracker is built. What it does is in [PRD.md](PRD.md). Status and file-format facts are in [NOTES.md](NOTES.md).

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Language | Python, managed with uv | The parser already works. The standard library covers XML, zip, `struct` (map `.bin`), `sqlite3` and `http.server` |
| Runtime dependencies | Standard library only until the desktop phase, then `pywebview` | Keeps running and packaging simple |
| Dev dependencies | `pytest` | |
| Code layout | A `celeste_tracker/` package, replacing the single script | The script is ~670 lines, and the later items add a store, a server and a `.bin` parser |
| Storage | SQLite file in the user data folder (never in the repo) | Needed for snapshots (dates), editable fields and caches. `sqlite3` is in the standard library |
| UI | One HTML/JS page that reads the JSON API. First served by `celeste-tracker serve` in the browser, then shown in a `pywebview` desktop window | The same page works in both. No build step while the UI is small |
| Distribution (later) | PyInstaller `.exe` for Windows players | Players don't need Python, uv or WSL |

Users today: only the author, running from WSL. Later: other players, mostly on Windows. Choices that only matter for other players (installer, auto-detecting the Celeste folder, a desktop window) can wait, but nothing should block them. In particular, the core must not assume WSL paths.

## Layers

```
read-only sources              core                                       front ends
Saves/N.celeste   ─┐
Mods/*.zip        ─┼─► parse ─► model ─► rules ─► JSON (versioned) ─┬─► CLI text / markdown
Maps/*.bin (later)─┘    ▲                                            ├─► serve: local page (browser)
                        │                                            └─► desktop: same page in pywebview
                        └── store (SQLite): mod-scan cache, user fields, snapshots
```

- **Sources are read-only** (PRD #11). Only the store is written.
- **Front ends never parse files.** They get the JSON (PRD #10). The CLI renders the same data as the UI.
- **Rules are one module.** The completion definition from the PRD lives in one place.

## Package layout

```
celeste_tracker/
  paths.py      find Saves and Mods (per OS, config file, CLI flags)
  save.py       .celeste XML -> raw records (slot, sets, areas, sides, session)
  mods.py       zip / folder scan: map list, sides per map, dialog titles, mod names
  binmap.py     (later) map .bin: checkpoints, berries, whether a side has a heart
  model.py      dataclasses: Slot > LevelSet > Map > Side
  rules.py      side / map / set status, from the PRD's definition
  store.py      SQLite: user fields, mod-scan cache, snapshots
  export.py     model -> JSON
  cli.py        argparse, text and markdown rendering
  web/          server.py + static/index.html, app.js (later)
tests/
  fixtures/     small made-up .celeste files and mod zips, safe to commit
```

## Data model

The side is the unit (PRD, Definition of "completed"). Everything else rolls up.

```
Slot      number, path, last_played_sid, session (sid, side, room, deaths)
LevelSet  name, title, mod_name, loaded, maps[]
Map       sid, title, sides{A, B, C}
Side      exists        known from the mod files (A/B/C .bin); vanilla from a hardcoded list
          cleared, heart, deaths, ticks, best_ticks, best_deaths, berries
          checkpoints_reached[]
          has_heart     true / false / unknown (needs binmap.py; vanilla hardcoded)
          status        not opened | in progress | cleared, no heart | completed
```

- A side with `has_heart = false` is completed once cleared. While `has_heart` is unknown (mods, until `.bin` parsing), a cleared side without its heart shows **cleared, no heart**, not completed. That way the tool never claims more than the save shows.
- Placeholder B/C records in the save (the save always lists three) are dropped when the mod files show the side doesn't exist.
- Totals: sides done / sides total is the main number, maps done / maps total next to it.

## JSON export

```json
{"schema": 1, "generated_at": "…", "slots": [{"number": 1, "sets": [{"name": "…", "maps": [{"sid": "…", "sides": {"A": {…}}}]}]}]}
```

The `schema` number goes up on breaking changes, so the UI can tell what it got.

## Store (SQLite)

Location: `%APPDATA%\celeste-tracker\` on Windows, `~/.local/share/celeste-tracker/` on Linux/WSL, `~/Library/Application Support/celeste-tracker/` on macOS. The config file (`config.toml`, read with `tomllib`) sits next to it.

| Table | Holds | Notes |
|---|---|---|
| `user_fields` | key (set or map ID), notes, difficulty, rating, dropped | Replaces `celeste_notes.json` (moved over on first run) |
| `mod_cache` | zip path, size, mtime, scanned data | Skips re-reading unchanged zips; matters on `/mnt/c` and for `.bin` parsing |
| `snapshots` | taken_at, slot, sid, side, cleared, heart, deaths, ticks, berries | One row only when a side's values changed since the last row. "Cleared on" = first row with `cleared` true; "last played" = last row where deaths or ticks went up |

Snapshots are only taken when the tool runs. Dates are "seen by" dates, as precise as how often it runs. The desktop app can take one on launch.

## Testing

- `pytest` with fixtures in `tests/fixtures/`: small hand-written saves and mod zips covering B/C folding, B/C-only maps, AltSidesHelper `-D` maps, placeholder sides, the recycle bin and the session. Real saves never go in git.
- Before committing, also run against the author's real slots 1 and 31 locally. Later: keep their JSON output in `local/` and diff it after changes.

## Build order

1. Split the script into the package, keeping today's output, and add tests.
2. Side-based model and rules (PRD #6, #7) and `--json` (#10).
3. All slots (#8), mod name (#9), config file.
4. Store: move notes over, add user fields, cache the mod scan.
5. `serve` UI.
6. Snapshots (dates), `binmap.py` (checkpoint and berry totals, heart presence).
7. For other players: `pywebview` window, PyInstaller build, auto-detect the Celeste folder.

## Open design questions

- Desktop shell: `pywebview` is the plan. Revisit Tauri only if the Python window falls short (size, look, auto-update).
- Whether the UI needs a framework (Preact or Svelte) once it has filters and editing. Start without one.
