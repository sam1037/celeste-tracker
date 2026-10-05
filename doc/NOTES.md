# Celeste mod progress tracker: notes

Build status, the save and mod file format, and open technical questions. What to build and why is in [PRD.md](PRD.md).

## Status

| # | Requirement (see PRD) | Status |
|---|---|---|
| 1 | Progress per mod and level set | per level set: done (sides done/total is the main number, maps done/total next to it). Per mod: todo (DESIGN step 4) |
| 2 | In-game titles | done (`--mods`, from each mod's `Dialog/English.txt`; vanilla titles are built in) |
| 3 | Real map and side totals | per level set: done (`--mods`, from the zips' `Maps/` lists). Per mod: todo. `-B`/`-C` files fold into their map. Vanilla's chapters and sides are built in |
| 4 | Detail view of one set | done (`--set`): one row per side |
| 5 | Checkpoints per side and saved room | done |
| 6 | Status per side | done (`rules.side_status`) |
| 7 | Completion rules | done (`rules.py`). Vanilla knows which sides have no heart; for mods that's unknown until `.bin` parsing, so a cleared side without its heart shows "cleared, no heart" and doesn't count as done |
| 8 | All slots in one view | partly: `--all` lists every slot's sets with a Slot column (repeats a set once per slot). Combined view (one row per mod, best status per side): todo, DESIGN step 4. An unreadable slot is skipped with a warning |
| 9 | Mod name | partly. Today the Mod column shows the mod ID from `everest.yaml` (first top-level `Name:`), else the zip or folder name; when several mods add maps to one set, the one adding the most names it. GameBanana titles and the fallback rule: todo (DESIGN step 4) |
| 10 | JSON export | done (`--json FILE`, `-` for stdout), schema 1. All 32 of my slots: 11 MB, mostly the 2,119 "not started" sets the save lists |
| 11 | Read-only | holds today, keep it |
| 12 | Offline, nothing sent | holds today (no network use yet) |

Should have: the config file is done (`--save-config`, `config.toml` in the user data folder). Extra stats and user fields are todo.

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
- Map files: `Maps/<set>/<map>.bin` is the A side; `<map>-B.bin` and `<map>-C.bin` are its B and C sides. The save stores all three under the one SID `<set>/<map>`. Only `-B` and `-C` are sides: `-D` files (e.g. `MtEverest/0/MtEverest-D`) are maps of their own in the save. A map can have no A file: `isafriend/blizzard/1-blizzard` has only `-B` and `-C`.
- AltSidesHelper: a map can list extra sides in `Maps/<set>/<map>.altsideshelper.meta.yaml` (`Sides: - Map: "MtEverest/0/MtEverest-D"`, `Preset: "d-side"`). In game they show as more sides of that chapter, but each is its own `.bin` and its own `AreaStats` in the save, and the name isn't always `-D` (Glyph's is `BeefyUncleTorre/map/z-1-D`). ~17 mods in my Mods folder use it. We count them as maps (see the PRD's definition), so the tracker doesn't need to read these files.
- Vanilla: only chapters 1-7 and Core have B/C sides. Prologue, Epilogue and Farewell are stored with `HeartGem=false` even when cleared (checked on all 32 slots), so they count as having no heart.
- Slot files are `N.celeste`. The Saves folder also holds `N-modsave-*`, `N-modsession-*`, `modsettings-*`, `settings.celeste` and `debug.celeste`.
- A save lists every level set Everest has registered, played or not, and its own empty `LevelSetStats Name="Celeste"` (vanilla's chapters are in the top-level `<Areas>`).
- Slots (2026-10-05): all 32 have progress; 63 of 288 played level sets are played in more than one slot, 29 of them with different progress (Sentient Forest in 6 slots). Slots 1-31 each show vanilla at 1/27: the Prologue is cleared on every new slot.
- Only one level set gets chapters from two mods: `BeefyUncleTorre/map` (Glyph: 6, Glyph D side: 1). No side file is in two zips, and no chapter's sides are spread over different mods.
- Mods folder (2026-10-05): 265 mods with maps. 204 have one map, 237 have one level set. Spring Collab 2020 has 105 maps in 7 level sets. Map titles repeat across mods ("Prologue" in 13).
- Everest's mod database (fetched 2026-10-05): `everest_update.yaml` (1.2 MB) has the mod ID as top-level key and `GameBananaFileId`. `mod_search_database.yaml` (13.5 MB) has entries with `Name` (the GameBanana title), `Author` and `Files: - ID: GameBanana/<file id>`. Joined: a GameBanana title for 260 of my 265 map mods (not OmoriPack). For one-map mods, the map title equals the GameBanana title in 161 of 199 cases, the mod ID only in 121. Some titles carry update notes ("MINDCRACK C-Sides Update! MINDCRACK Map Pack"); Spring Collab 2020's is "The 2020 Celeste Spring Community Collab".
- `everest.yaml`: the mod's `Name:` isn't always the first line (`- DLL:` can come first); dependency entries have their own, deeper-indented `Name:`.
- Windows saves: `C:\Program Files (x86)\Steam\steamapps\common\Celeste\Saves` (from WSL: `/mnt/c/...`). Mac: `~/Library/Application Support/Celeste/Saves`.

## Known issues

- None open. (Fixed: `--mods` used to count `-B.bin` / `-C.bin` as separate maps, 81 of 1,324 in my Mods folder.)

## Open technical questions

- Which mod sides have no heart (the PRD treats those as completed once cleared): probably needs the `.bin`. Until then, a cleared side with `HeartGem=false` can't be told apart from one whose heart was skipped.
- Is the JSON too big for the UI? Decide in the UI step whether to drop "not started" sets or split the file.

## TODO

- See how players track progress manually in Excel sheets, to find which columns matter. First pass (2026-10-04): no public personal sheets found. The community challenge lists (Hardest Maps Clear List, goldberries.net) give each side its own entry and mark the level of clearing (clear, full clear, golden). This is why the side became the unit. Real personal sheets would still help: ask in r/celestegame or the Celeste Discord.
- Next build step: DESIGN.md step 4, mods as the top level with GameBanana names. (Answers the old "Mod name?" note.)
