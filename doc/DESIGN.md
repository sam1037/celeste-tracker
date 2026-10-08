# Celeste mod progress tracker: design

How the tracker is built. What it does is in [PRD.md](PRD.md). Status and file-format facts are in [NOTES.md](NOTES.md).

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Language | Python, managed with uv | The parser already works. The standard library covers XML, zip, `struct` (map `.bin`), `sqlite3` and `http.server` |
| Runtime dependencies | Standard library only, plus `pywebview` for the desktop window, as the optional `desktop` extra | The CLI and `--serve` stay standard library only |
| Dev dependencies | `pytest`; `pyinstaller` in the `build` group | |
| Code layout | A `celeste_tracker/` package, replacing the single script | The script is ~670 lines, and the later items add a store, a server and a `.bin` parser |
| Storage | SQLite file in the user data folder (never in the repo) | Needed for snapshots (dates), editable fields and caches. `sqlite3` is in the standard library |
| Mod names | GameBanana titles from Everest's public mod database (maddie480.ovh), downloaded with `urllib`, cached in the user data folder | The zip only holds the mod ID; the title players know is only on GameBanana. Optional: everything works offline |
| UI | One HTML/JS page that reads the JSON API. First served by `--serve` in the browser, then shown in a `pywebview` desktop window | The same page works in both. No build step while the UI is small |
| Distribution | PyInstaller builds from GitHub Actions, published as GitHub releases: a Windows folder (zipped) and an unsigned macOS `.app` | Players don't need Python, uv or WSL. PyInstaller can't cross-build, so CI builds each OS on its own runner |

Users today: only the author, running from WSL. Later: other players, mostly on Windows. Choices that only matter for other players (installer, auto-detecting the Celeste folder, a desktop window) can wait, but nothing should block them. In particular, the core must not assume WSL paths.

## Layers

```
read-only sources                  core                                       front ends
Saves/N.celeste       ─┐
Mods/*.zip            ─┤
Maps/*.bin (later)    ─┼─► parse ─► model ─► rules ─► JSON (versioned) ─┬─► CLI text / markdown
Everest mod database  ─┘    ▲                                            ├─► serve: local page (browser)
(online, cached, optional)  │                                            └─► desktop: same page in pywebview
                            └── store (SQLite): mod-scan cache, user fields, snapshots
```

- **Sources are read-only** (PRD #11). Only the store and the caches in the user data folder are written.
- **Front ends never parse files.** They get the JSON (PRD #10). The CLI renders the same data as the UI.
- **Rules are one module.** The completion definition from the PRD lives in one place.

## Package layout

```
celeste_tracker/
  paths.py      find Saves and Mods (config file, CLI flags, else Olympus's installs, Steam libraries, Epic, itch)
  save.py       .celeste XML -> raw records (slot, sets, areas, sides, session)
  mods.py       zip / folder scan: map list, sides per map, dialog titles, mod IDs
  moddb.py      Everest's public mod database: mod ID -> GameBanana title, downloaded and cached
  binmap.py     (later) map .bin: checkpoint and berry totals, whether a side has a heart (information only)
  model.py      dataclasses: Slot > Mod > LevelSet > Map > Side
  rules.py      side / map / set / mod status, from the PRD's definition
  core.py       load_slot / load_slots: the one call front ends make (parse -> model -> rules)
  store.py      SQLite: user fields, mod-scan cache, snapshots (later)
  export.py     model -> JSON
  cli.py        argparse, text and markdown rendering
  web/          server.py + static/index.html, app.js, style.css, fonts/: the --serve page
  desktop.py    the page in a pywebview window, the folder picker, the browser fallback
packaging/      PyInstaller spec (.github/workflows/release.yml runs it)
tests/
  fixtures/     small made-up .celeste files and mod zips, safe to commit
```

## Data model

The side is the unit of progress (PRD, Definition of "completed"); rows are mods. The model keeps **what exists** (the catalog, the same for every slot) apart from **what the player did** (progress, one per slot).

```
Catalog: one, built from the Mods folder, the vanilla list, and any chapter a slot mentions that neither knows;
         collab gyms (level sets named `Gyms`, `0-Gyms`, ...) are left out (model.is_gym, PRD)
  Mod       id            everest.yaml Name; "Celeste" for vanilla; the level set name if no mod was found
            name          what players see (rule below); name_source: gamebanana | map title | level set title | mod id
            gamebanana_title, found (is in the Mods folder), sets[]
  LevelSet  name, title, chapters[]      the part of the level set this mod provides
  Chapter   sid, title, sides{A, B, C}   (a `Map` in code)
  Side      side, exists                 known from the mod files (A/B/C .bin); vanilla from a hardcoded list
            has_heart                    true / false / unknown (vanilla hardcoded); information only

Progress: one per slot
  Slot          number, path, last_played_sid, session (sid, side, room, deaths), not_loaded{level set names}
  SideProgress  per (slot, chapter SID, side): cleared, heart, deaths, ticks, best_ticks, best_deaths,
                berries, checkpoints_reached[]
```

`rules.py` combines the two into a **view**: every catalog node (mod, level set, chapter, side) gets a status and totals, either for one slot or for all slots (below: each mod from its furthest slot). Front ends only read views. Mods, level sets and chapters get a view for every slot their mod was played in (so an unplayed tier shows as not started); sides only have views for slots where they were opened, so a missing view means "not opened".

Side status: completed (= cleared) / in progress / not opened. Map status: completed / in progress / not opened. Level set status: complete, in progress, started, not started, or all opened done (no mod files, so the totals only cover what was opened). A mod's status uses the same values, computed over all its sides; its totals are the sums of its sets.

- A side is completed when it's cleared; crystal hearts don't count (PRD). Each view also counts `hearts` collected, as information.
- Placeholder B/C records in the save (the save always lists three) are dropped when the mod files show the side doesn't exist.
- Totals: sides done / sides total is the main number, maps done / maps total next to it.

### All slots (the default view): each mod's furthest slot

- **Each mod shows one slot's progress: the slot that got furthest in it.** Furthest = most sides completed, then most sides opened, then most checkpoints reached on unfinished sides, then most time played. The whole mod (every level set, chapter and side) comes from that slot, so its numbers are one real save's: nothing is added up or mixed across slots.
- The `"all"` view of every node in the mod is a copy of that slot's view, with `slot` = the chosen slot and `slots` = every slot the node was played in. The per-slot views stay, so "also played in: slot 1 (2/3), slot 31 (0/3)" can be shown.
- Checked on the author's 32 slots (2026-10-05): of the 59 mods played in more than one slot, the furthest slot already has every side completed in any slot, so nothing is lost. (The earlier per-side merge added up deaths, time and berries, which double-counted berries, and could call a chapter complete from two different slots.)
- `[not loaded]` and the latest checkpoint come from the chosen slot too.
- One slot is a filter on the same view (`--slot N`, and a slot picker in the UI).

### Grouping level sets into mods

- **A chapter belongs to the mod whose zip holds its `.bin` file**, so rows match Olympus: one per zip. A level set split across mods appears under each, with that mod's chapters. In the author's Mods folder this happens once: Glyph's `BeefyUncleTorre/map` gets 6 chapters from Glyph and 1 (`z-1-D`) from Glyph D side, which are two rows.
- Not seen in the author's Mods folder, but handled: if the same file is in several zips, the mod with more chapters in that level set takes it; a B/C side file in a different zip than its A side goes with the A side's mod.
- A chapter in a save that no mod in the Mods folder has (removed, or `--mods` not used) goes to a mod named after its level set, `found = false`, named by the set's title or ID.
- Vanilla is the mod "Celeste" with one level set.

### Mod names (PRD #9)

The first one available wins:

1. **GameBanana title**, from the mod database (below).
2. **Map title**, if the mod has one map. True for 204 of the 265 map mods in the author's Mods folder, and for 161 of the 199 that GameBanana lists, the map title is exactly the GameBanana title.
3. **Level set title**, if the mod has one level set.
4. **Mod ID** from `everest.yaml` (what the Mod column shows today).

Map titles can't name a mod in general: a collab has one per map (Spring Collab 2020 has 105), and generic titles repeat across mods ("Prologue" is in 13 mods). Later, the user can rename a mod (PRD, Should have); a rename wins over all of the above.

### Showing the tree

The CLI and the UI show the same tree: mod > level set > chapter > side. **A level with only one entry is skipped**: a mod with one level set shows its chapters directly, and a chapter-level row is skipped when the mod has one chapter, so Sentient Forest opens straight to its A/B/C sides. 237 of the author's 265 map mods have one level set, and 204 have one chapter. In code a chapter is a `Map` (keyed by its SID); user-facing text says "chapter".

## Mod database (online, optional)

Everest publishes two files that Olympus and Everest's updater use:

| File | Size | What we read |
|---|---|---|
| `https://maddie480.ovh/celeste/everest_update.yaml` | ~1.2 MB | top-level key = mod ID (everest.yaml `Name`) → `GameBananaFileId` |
| `https://maddie480.ovh/celeste/mod_search_database.yaml` | ~13.5 MB | each entry: `Name` (GameBanana title), `Author`, `Files: - ID: GameBanana/<file id>` |

Mod ID → file ID → title. Example: `SonderCrispy` → file 1669303 → "Sonder" by Crispybag.

- `moddb.py` downloads both with `urllib` (gzip: ~3 MB instead of 13.5), keeps only the mod ID → {title, author} map (~460 KB), and saves it as `moddb.json` next to the config file. It refreshes when the cache is older than 7 days. `--refresh-moddb` forces a refresh, `--offline` never connects.
- No YAML library: a small line parser reads only the keys above. Tests cover it with trimmed copies of both files.
- When the download fails (no internet, site down), it uses the old cache, or falls back to rules 2-4 with a one-line note. Nothing ever fails because of the network.
- Privacy (PRD #12): plain GET requests for public files, with a User-Agent naming the tool. Nothing about the player's saves or mods is sent.
- The cache is a file, not a store table: it's downloaded data that can be rebuilt any time.

## JSON export

```json
{"schema": 2, "generated_at": "…",
 "slots": [{"number": 1, "path": "…", "last_played_sid": "…", "session": {…}}],
 "mods": [{"id": "…", "name": "…", "progress": {"all": {…}, "1": {…}},
           "sets": [{"name": "…", "progress": {…},
                     "chapters": [{"sid": "…", "title": "…", "progress": {…},
                                   "sides": {"A": {"has_heart": null, "progress": {"all": {"status": "…", …}, "1": {…}}}}}]}]}]}
```

One catalog tree. Every node carries `progress`, keyed by `"all"` (the mod's furthest slot, named in `slot`) and by slot number, with the status and totals `rules.py` computed, so the UI never applies rules itself. Schema 1 had a separate tree per slot. Mod, level set and chapter views also have `by_side`, the sides done and total per letter (finished vanilla: `{"A": [11, 11], "B": [8, 8], "C": [8, 8]}`), for the page's A/B/C strip ([UI.md](UI.md)); it was added without a schema bump, since nothing that existed changed.

The `schema` number goes up on breaking changes, so the UI can tell what it got.

## Store (SQLite)

`tracker.db`, next to the config file (`config.toml`, read with `tomllib`) in the user data folder: `%APPDATA%\celeste-tracker\` on Windows, `~/.local/share/celeste-tracker/` on Linux/WSL, `~/Library/Application Support/celeste-tracker/` on macOS. A `--config` elsewhere moves the store and the mod list cache with it (that's how tests stay off the real files). WAL mode with `synchronous=NORMAL`: commits don't wait for an fsync, which costs 100+ ms on WSL's disk.

| Table | Holds | Notes |
|---|---|---|
| `meta` | schema version, whether the old notes were imported | A store from a newer version is refused |
| `user_fields` | key (mod ID, level set or chapter SID), note, difficulty (free text), rating (1-5), dropped, rename (mods only) | A rename wins over every other mod name. The first run with the real store imports `celeste_notes.json` once; `--import-notes FILE` does it by hand |
| `mod_cache` | zip path, size, mtime, what was read from it (JSON) | Unchanged zips aren't reopened. With the stat calls on a thread pool, the scan of ~450 zips on `/mnt/c` takes 0.1 s warm (was 3-7 s) |
| `snapshots` (maybe later) | taken_at, slot, sid, side, cleared, heart, deaths, ticks, berries | One row only when a side's values changed since the last row. "Cleared on" = first row with `cleared` true; "last played" = last row where deaths or ticks went up |

Snapshots are only taken when the tool runs. Dates are "seen by" dates, as precise as how often it runs. The desktop app can take one on launch.

## UI (`--serve`)

How the page looks (tokens, the side strip, layout) is in [UI.md](UI.md). This section is how it's built.

- `web/server.py`: `http.server` on 127.0.0.1 only, single-threaded. `GET /` serves `static/index.html`, `app.js` and `style.css` (nothing else); `GET /api/library` is the schema 2 JSON (compact, ~2.3 MB for the author's 32 slots, built once per change in ~0.1 s and kept in memory) plus a `version`; `GET /api/status` returns the version; `POST /api/user {key, field, value}` sets one store field.
- The server keeps the parsed slots in memory. An edit rebuilds the model from them (no file reads); `/api/status` and `/api/library` stat the slot files (on a thread pool) and reparse when one changed, so the page, which polls `/api/status` every 5 s, follows the game's saves. `?refresh=1` also rescans the Mods folder.
- Security: requests must name `localhost`/`127.0.0.1` in `Host` (DNS rebinding); POSTs need the `X-Celeste-Tracker: 1` header, which a page on another site can't send without a CORS preflight the server never answers. The page puts every string through `esc()`; verified in Chrome with a mod renamed to an `<img onerror>` payload.
- `app.js` applies no rules: statuses and totals come from the JSON. It filters, sorts and draws: mod rows → level sets (collabs only) → chapters → sides, skipping a level with one entry. View state (slot, filter, sort, search, open mods / level sets / chapters) is in the URL hash.
- No framework and no build step: ~400 lines of JS. Revisit if the UI grows.

## Desktop app

For players who don't use a terminal: `celeste_desktop.py` (`celeste_tracker/desktop.py`) is what the downloads run.

- **Same page, same server.** It starts the `--serve` server on a free port (port 0, so it never clashes with another copy or a `--serve`) on a daemon thread, and shows `http://localhost:<port>/` in a pywebview window: Edge WebView2 on Windows (part of Windows 11 and updated Windows 10), WebKit on macOS. Nothing in the page knows it's in a window.
- **Finding the game.** The config file's `saves` first, else `paths.find_saves_dir()`: Olympus's `config.json` (it lists the installs it manages; `%LOCALAPPDATA%\Olympus` on Windows), every Steam library (the registry's `SteamPath`, then `steamapps/libraryfolders.vdf` for other drives), the Epic and itch folders, then the OS's usual user folders. A folder with save slots wins over an empty one. The Mods folder is Everest's next to Saves, else one in a known Celeste folder.
- **Nothing found:** the window shows a "Where is Celeste?" page with a folder picker (pywebview's dialog), accepts the Celeste folder or the Saves folder, and writes `saves` to the config file.
- **No window possible** (pywebview missing, no WebView2, no GTK or Qt on Linux): the page opens in the default browser, with tkinter's folder picker if needed.
- **Downloaded zips:** Explorer marks every unzipped file as "from the internet" (a `Zone.Identifier` stream), and .NET then refuses to load pythonnet's `Python.Runtime.dll`, so the window failed and the page opened in the browser (found 2026-10-08 on the first CI build). The Windows build removes that mark from the DLLs in its own folder before loading pywebview (`desktop.unblock_dlls`). SmartScreen's "unknown publisher" warning on the exe stays; that one needs code signing.
- **Logs:** a windowed build has no console, so notes and errors go to `desktop.log` next to the config, which a player can attach to a bug report.
- **Build:** `packaging/celeste-tracker.spec`, a one-folder build (starts faster and gets fewer antivirus false alarms than one file), no UPX. `.github/workflows/release.yml` runs the tests, then builds on `windows-latest` and `macos-latest`; a `v*` tag publishes both zips as a GitHub release. The macOS app is unsigned: players open it through System Settings > Privacy & Security > Open Anyway. Signing costs $99/year and waits until Mac players ask.

## Testing

- `pytest` with fixtures in `tests/fixtures/`: small hand-written saves and mod zips covering B/C folding, B/C-only maps, AltSidesHelper `-D` maps, placeholder sides, the recycle bin and the session. Real saves never go in git.
- Before committing, also run against the author's real slots 1 and 31 locally. Later: keep their JSON output in `local/` and diff it after changes.
- The server: `tests/test_server.py` runs it on a free port (pages, API, host check, header check, edits, picking up a changed save).
- The page: drive it with `playwright-cli` (Playwright's Chromium; its Claude Code skill is committed in `.claude/skills/`, and it works on Windows/WSL and macOS) against a server with a scratch `--config`: read the element tree, click, read the console, take screenshots. Views are opened through the URL hash. On WSL, the Windows Chrome in headless mode also gives one-shot screenshots (`--screenshot`) or the rendered DOM (`--dump-dom`), but won't make a window narrower than ~500 px.

## Build order

1. Split the script into the package, keeping today's output, and add tests. (done)
2. Side-based model and rules (PRD #6, #7) and `--json` (#10). (done)
3. All slots (#8), mod name (#9), config file. (done)
4. Mods as the top level (PRD #1, #3, #8, #9, #12): catalog / progress split, chapters grouped by zip, the all-slots view as the default (`--slot N` filters; since 2026-10-05 each mod shows its furthest slot instead of a per-side merge), `moddb.py` and GameBanana names, JSON schema 2. The overview gets one row per mod, with the level sets indented under a mod that has several; `--set` also accepts a mod name. (done; the combined CLI view leaves out the long unfinished-chapters list and points to `--set` / `--slot N`)
5. Store: move notes over, add user fields and mod renames, cache the mod scan. (done)
6. `--serve` UI. (done)
7. For other players: `pywebview` window, PyInstaller build, auto-detect the Celeste folder. (in progress, see Desktop app)

## Maybe later

Not planned; worth doing if the need shows up.

- **Snapshots, for dates.** The save has no dates (`LastSave` is always `0001-01-01`), so "cleared on" and "last played" need the `snapshots` table (see Store): a row per side whenever its values change between runs. Dates would only be as precise as how often the tool runs.
- **`binmap.py`, reading the map `.bin` files.** Checkpoint totals per side ("checkpoint 3/6"), berry totals per chapter, and whether a side has a heart at all ("hearts 12/20"). The save only lists what was reached. Results would go in the mod-scan cache.

## Open design questions

- Desktop shell: `pywebview`. Revisit Tauri only if the Python window falls short (size, look, auto-update).
- Whether the UI needs a framework (Preact or Svelte) once it has filters and editing. Start without one.
