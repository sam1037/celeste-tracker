# Celeste mod progress tracker: notes

Build status, the save and mod file format, and open technical questions. What to build and why is in [PRD.md](PRD.md).

## Status

| # | Requirement (see PRD) | Status |
|---|---|---|
| 1 | Progress per mod and level set | done. One row per mod; a mod with several level sets lists them underneath. Sides done/total is the main number, chapters done/total next to it |
| 2 | In-game titles | done (`--mods`, from each mod's `Dialog/English.txt`, including values on the lines under their key; vanilla titles are built in) |
| 3 | Real chapter and side totals | done, per level set and per mod (`--mods`, from the zips' `Maps/` lists). `-B`/`-C` files fold into their map. Vanilla's chapters and sides are built in |
| 4 | Detail view | done (`--set`): one mod or one level set, one row per side; a one-chapter mod goes straight to its sides; in the all-slots view, which slot is shown and the other slots with their counts |
| 5 | Checkpoints per side and saved room | done |
| 6 | Status per side | done (`rules.side_status`) |
| 7 | Completion rules | done (`rules.py`): a side is completed when cleared; hearts are counted separately. Collab gyms are left out of the catalog (`model.is_gym`) |
| 8 | All slots in one view | done: the default. Each mod shows its furthest slot (`rules.furthest_slot`), named in the Slot column: the CLI shows "8 (+5)" (5 other slots), the page only the number, with the other slots in its tooltip and the opened mod's facts (2026-10-08); `--set` lists the other slots with their counts. `--slot N` for one slot. An unreadable slot is skipped with a warning. (Until 2026-10-05 sides were merged across slots, which double-counted berries) |
| 9 | Mod name | done. GameBanana title from the mod list (260 of my 272 mods), else chapter title, level set title, mod ID (OmoriPack shows "Cold") |
| 10 | JSON export | done (`--json FILE`, `-` for stdout), schema 2: one catalog tree, progress per slot and `all`. All 32 of my slots: 5.6 MB indented, 2.3 MB compact (what `--serve` sends) |
| 11 | Read-only | holds today, keep it |
| 12 | Offline, nothing sent | holds. The only network use is two GETs for the public mod list, at most weekly (`--offline` to skip); the cache is `moddb.json` next to the config |

UI (Later): `--serve` done, see DESIGN "UI". Desktop window and downloads done (DESIGN step 7, "Desktop app"): **v0.1.0 released 2026-10-08** on GitHub Releases, a Windows folder and an unsigned macOS app built by `.github/workflows/release.yml`. Verified on real machines: the Windows build from CI (opens its window from a downloaded zip, finds the Steam Saves and Mods folders with no config: 32 slots, 273 mods), the folder picker on Windows (a wrong folder gives the message, the Celeste folder loads and is saved), the macOS build (opens its window, found the Mac's saves by itself), the icon in the exe. Not verified yet: the browser fallback without WebView2, and Olympus's `config.json` on a real file (the reader follows Olympus's public format, `installs: [{path}]`; on the author's PC Steam finds the game first).

Should have: config file done (`--save-config`). User fields done, per mod: note, rating (`--rate`, 1-5), difficulty (Beginner to Grandmaster), tags (`--tag`/`--untag`), dropped (`--drop`/`--undrop`), mod rename (`--rename`), in `tracker.db` next to the config. The page edits rating, difficulty, tags and note (UI.md "Your fields"); dropped and rename are CLI-only. Extra stats (best time, best deaths, berries per side) are in the model and JSON; the page has Best and Berries columns, hidden at first (Columns menu), and best deaths isn't shown anywhere yet.

Technical notes on the "Later" items:

- Checkpoint and berry totals need parsing the map `.bin`. The save only lists what was reached.
- Dates aren't in the save (`LastSave` is always `0001-01-01`), so they need snapshots between runs.

## Hierarchy

1. **Save slot:** one `N.celeste` file (plus `N-modsave-*`, `N-modsession-*` side files).
2. **Level set:** a folder of maps. Its name is the map SID minus the last part, e.g. `SpringCollab2020/4-Expert`. In the save: `LevelSetStats Name="…"`. Vanilla chapters are in the top-level `<Areas>`.
3. **Map:** what the game calls a chapter. One `AreaStats`, identified by its SID, e.g. `NotPhobos/Omori/Snow Mountain`.
4. **Side (mode):** A, B or C. One `AreaModeStats` each. The save always lists three, even when the map has no B/C side. This is where `Completed`, `HeartGem`, `Deaths`, `TimePlayed`, `BestTime` and `Checkpoints` live.
5. **Checkpoint:** a room flagged as a checkpoint. The save lists the reached ones per side as room IDs (`<Checkpoints><string>9b</string>`); the map start is never listed.

- **Mod vs level set:** a mod is one zip. One zip can hold several level sets (a collab is often split by difficulty: `0-Lobbies`, `1-Beginner`, …) or none (code-only mods).
- **Three names for one thing:** Olympus/zip `OmoriPack` → save `NotPhobos/Omori/Snow Mountain` → in game "The Hikkikomori Route" / "Cold". Only the zip contents link them.

## Save and mod file facts (verified on real saves)

- `TimePlayed` is in ticks: 10,000,000 per second.
- Sets in `<LevelSetRecycleBin>` = mods Everest didn't load at the last save (shown as `[not loaded]`). Their progress is kept.
- `LastArea_Safe` = last-played map. `CurrentSession_Safe` = the Save & Quit point: `Level` (room), `StartCheckpoint`, `Deaths`, `RespawnPoint`. One per slot.
- Dialog keys: the ID with `/`, spaces and `-` replaced by `_`. Set `NotPhobos_Omori`, map `NotPhobos_Omori_Snow_Mountain`, checkpoint `NotPhobos_Omori_Snow_Mountain_c_01`.
- Dialog values can start on the line under the key: `StrawberryJam2021_5_Grandmaster_Hydro=` then `  Shattersong`, and every following line that isn't a `key=` line continues the value (credits run over several lines). The game shows these as the titles, so it reads them the same way; that a key must be one word (`\w+`) before the `=` is inferred from the game's parser, not checked. Strawberry Jam writes all its titles this way, and its map files are named after their authors (`5-Grandmaster/Hydro.bin`), so before 2026-10-05 its chapters showed author names. Next to each title it has `<key>_author` ("by Hydro & more") and `<key>_collabcredits`, which the tracker doesn't use. Spring Collab 2020 writes `key=value` on one line. In my Mods folder (2026-10-05), 10 mods have map or level set titles on the next line (Strawberry Jam: 134 titles; the other 9: 1-4 each, e.g. BreezeContest, intermediatecontest, SecretSantaCollab2024), and one (Solaris) ships its `English.txt` as UTF-16 with a BOM; reading both added 158 titles and changed no title that was already found. The tracker also accepts spaces before the `=` (one mod writes `KaileyTheAlien_CreationThroughSuffering = …`).
- Collab gyms (2026-10-05): level sets whose last part is `Gyms`, after an optional number prefix (`model.is_gym`, case-insensitive). In my Mods folder and all 32 slots this matches exactly `SpringCollab2020/0-Gyms` (5 maps), `StrawberryJam2021/0-Gyms` (6), `CatCollab/0-Gyms` (1) and `SecretSanta2024/3-Hard/WatchtowerContest/0-Gyms` (1); no other level set or map SID contains "gym". `Etaleanic/TechPractice` is a mod of its own and stays. Hiding them: Spring Collab 75/105 → 75/100 sides, Strawberry Jam 69/128 → 69/122 (all slots).
- Collab lobbies (2026-10-07): CollabUtils2 collabs keep their hub maps in a level set named exactly `<collab>/0-Lobbies` (25 mods in my Mods folder and saves, `model.is_lobby`). It holds one lobby map per tier, often plus a `0-Prologue`, and its dialog title is the collab's own name ("Spring Collab 2020"), so it read like a copy of the mod. Lobbies are real maps with their own deaths, time and clears (the game counts time and deaths while you walk through the hub), so they stay and count; the tracker adds " (lobby)" to the level set's title. A tier's chapters are in the level set named after its lobby map (`ABuffZucchiniCollab/0-Lobbies/1-Lobby` leads to `ABuffZucchiniCollab/1-Lobby`); when that level set has no title of its own, the tracker shows its folder name ("1-Lobby").
- Map files: `Maps/<set>/<map>.bin` is the A side; `<map>-B.bin` and `<map>-C.bin` are its B and C sides. The save stores all three under the one SID `<set>/<map>`. Only `-B` and `-C` are sides: `-D` files (e.g. `MtEverest/0/MtEverest-D`) are maps of their own in the save. A map can have no A file: `isafriend/blizzard/1-blizzard` has only `-B` and `-C`.
- AltSidesHelper: a map can list extra sides in `Maps/<set>/<map>.altsideshelper.meta.yaml` (`Sides: - Map: "MtEverest/0/MtEverest-D"`, `Preset: "d-side"`). In game they show as more sides of that chapter, but each is its own `.bin` and its own `AreaStats` in the save, and the name isn't always `-D` (Glyph's is `BeefyUncleTorre/map/z-1-D`). ~17 mods in my Mods folder use it. We count them as maps (see the PRD's definition), so the tracker doesn't need to read these files.
- Hearts (2026-10-05, all 32 slots): 4 vanilla sides (Forsaken City A) and 57 mod sides are cleared without the heart, all A sides; no B or C side is. Vanilla A-side hearts are hidden collectibles; B/C-side hearts end the level.
- Vanilla: only chapters 1-7 and Core have B/C sides. Prologue, Epilogue and Farewell are stored with `HeartGem=false` even when cleared (checked on all 32 slots), so they count as having no heart.
- Slot files are `N.celeste`. The Saves folder also holds `N-modsave-*`, `N-modsession-*`, `modsettings-*`, `settings.celeste` and `debug.celeste`.
- A save lists every level set Everest has registered, played or not, and its own empty `LevelSetStats Name="Celeste"` (vanilla's chapters are in the top-level `<Areas>`).
- Slots (2026-10-05): all 32 have progress; 63 of 288 played level sets are played in more than one slot, 29 of them with different progress (Sentient Forest in 6 slots). Slots 1-31 each show vanilla at 1/27: the Prologue is cleared on every new slot.
- Only one level set gets chapters from two mods: `BeefyUncleTorre/map` (Glyph: 6, Glyph D side: 1). No side file is in two zips, and no chapter's sides are spread over different mods.
- Mods folder (2026-10-05): 265 mods with maps. 204 have one map, 237 have one level set. Spring Collab 2020 has 105 maps in 7 level sets (100 in 6 without its gyms). Map titles repeat across mods ("Prologue" in 13).
- Everest's mod database (fetched 2026-10-05): `everest_update.yaml` (1.2 MB) has the mod ID as top-level key and `GameBananaFileId`. `mod_search_database.yaml` (13.5 MB) has entries with `Name` (the GameBanana title), `Author` and `Files: - ID: GameBanana/<file id>`. Joined: a GameBanana title for 260 of my 265 map mods (not OmoriPack). For one-map mods, the map title equals the GameBanana title in 161 of 199 cases, the mod ID only in 121. Some titles carry update notes ("MINDCRACK C-Sides Update! MINDCRACK Map Pack"); Spring Collab 2020's is "The 2020 Celeste Spring Community Collab".
- `everest.yaml`: the mod's `Name:` isn't always the first line (`- DLL:` can come first); dependency entries have their own, deeper-indented `Name:`.
- Windows saves: `C:\Program Files (x86)\Steam\steamapps\common\Celeste\Saves` (from WSL: `/mnt/c/...`). Mac: `~/Library/Application Support/Celeste/Saves`.

## Known issues

- None open. (Fixed: `--mods` used to count `-B.bin` / `-C.bin` as separate maps, 81 of 1,324 in my Mods folder. Fixed 2026-10-05: titles on the line under their dialog key were read as empty, so Strawberry Jam showed its map file names, which are the authors' names; the mod-scan cache is versioned (`mods.READ_VERSION`) so zips cached before are read again.)

## Open technical questions

- Which mod sides have a heart at all (for a "hearts x/y" count): probably needs the `.bin`. Not needed for completion any more.
- Speed on WSL (2026-10-05): the default run takes 1.2 s (was 7 s), 3 s the first time the store is filled. Every file check on `/mnt/c` costs ~4 ms, so the Mods scan uses scandir, a thread pool for stat calls and zip reads, and the `mod_cache` table. The first run of the week adds ~4 s for the mod list.
- JSON size for the UI (settled): the page loads the whole library at once, compact (2.3 MB for 32 slots; rebuilding the model and the JSON after an edit or a save takes ~0.1 s), which is fine on localhost. Revisit only if it gets slow.

## TODO

- See how players track progress manually in Excel sheets, to find which columns matter. First pass (2026-10-04): no public personal sheets found. The community challenge lists (Hardest Maps Clear List, goldberries.net) give each side its own entry and mark the level of clearing (clear, full clear, golden). This is why the side became the unit. Real personal sheets would still help: ask in r/celestegame or the Celeste Discord.
- Next build step: an update notice (the page help is done, below). Snapshots and `.bin` parsing moved to DESIGN's "Maybe later".
- Releasing: bump `version` in `pyproject.toml`, commit, `git tag -a vX.Y.Z -m "..."`, `git push origin vX.Y.Z`; the workflow tests, builds and publishes. Never move a tag that was pushed: release the next patch instead.
- Desktop app, later: an update notice (check GitHub's latest release on start; players don't hear about new versions otherwise), a single instance (a second start opens a second window today), code signing if players hit SmartScreen or Gatekeeper too often.
- Page help: done (2026-10-08) as the first two ideas below, a ? button and the ? key opening a help panel; see UI.md "Help". The request (user, 2026-10-08): tell players how to use the page: rows open by clicking, columns sort by clicking their header, `/` jumps to the search, what the statuses, "slot 1 (+5)", ⊘ (not loaded) and "?" totals mean, and that the page updates by itself when the game saves. Ideas to compare, from mature tools:
  - An info or "?" button in the top bar that opens a short help panel (Linear and Notion keep a "?" in a corner; GitHub's help menu).
  - `?` opens a list of keyboard shortcuts (GitHub, Gmail, YouTube), next to `/` for the search.
  - Hints where they're needed, without a separate page: an empty search says what you can search for, the first opened mod points at the sticky rows, column headers keep their tooltips.
  - Avoid step-by-step tours that pop up on first open (Intro.js, Shepherd): they get in the way of a page opened every day, and would add a dependency.
- Branch `author-column` (2026-10-08), PR #2. Done: the Author column and search by author, from the GameBanana list; Slot instead of "Slots and tags" (the player's tags moved to the mod's second line); the Columns menu (show or hide any column but Mod); column resizing by dragging the line between two column names, kept in the store through `/api/prefs`; one height for every mod row; the help panel. See UI.md "Layout". Verified with Playwright on the real saves in Chrome, light and dark, and the line widths at 125% scaling. Still to do:
  - README: the `--serve` paragraph doesn't mention the Author column, the Columns menu, resizing or the help, and the screenshots and GIF in `doc/media/` still show "Slots and tags" and the old widths.
  - Desktop app: not tried as a Windows build yet. Check that column widths survive closing and reopening the window (that's why they're in the store, not localStorage) and that the help dialog opens in WebView2.
  - The narrow-screen layout wasn't rechecked after the column changes (phones aren't a target, UI.md "Brief").
- Branch `mod-notes-rating` (2026-10-10): the player's fields on the page, per mod. Done: the Rating column, the note on the mod's second line, the ✎ Edit button on the hovered row, the Yours panel (stars, difficulty, tags, note), difficulty as a fixed list and tags in the store and CLI, Difficulty and Tags columns that turn on with their first use, the Columns menu in two groups, the Filter panel instead of Show. Plan and three mockups: PLAN-notes-rating.md. Verified with Playwright on the real saves (all slots, scratch config) in Chrome, light and dark: rating by click and arrow keys, sorting, notes saving while typing, tags added, suggested and removed, the columns turning on with their notice, old settings without the new columns, filters and old `show=` bookmarks; the CLI on slots 1 and 31. Still to check:
  - Desktop app (WebView2, and WKWebView on macOS): that the edits are kept after closing the window, that the note field grows (it's sized in JS, as WKWebView has no `field-sizing`), and the tag suggestions (`<datalist>`).
  - The README's screenshots in `doc/media/` don't show the new columns or the Filter panel.
  - The page can't set dropped or rename yet; the Dropped filter is gone with Show.
- Columns, maybe later: when the column next to a dragged line is at its minimum, take the width from Sides instead of stopping; double-click a line to fit the column to its longest value (as in Excel and File Explorer) instead of resetting it; reach the resize lines with the keyboard. (Sorting by rating is back with the Rating column, 2026-10-10.)
- Author search, maybe later: the per-map `<key>_author` dialog lines of collabs ("by ethanol", 23 zips) as search words, so a mapper finds their map inside a collab. They aren't all authors, so they'd need care.
