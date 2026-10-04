# Celeste mod progress tracker

## Goal

Help a player understand their progress on Celeste mods: which mods are completed or not, where they stopped, and stats per mod. Start as a CLI (`celeste_progress.py`), add a UI later.

## Definition of "completed"

- **Map completed:** every side the map has (A, plus B and C if they exist) is cleared **and** has its heart.
- **Level set completed:** every map in the set is completed.
- No special handling for now: lobbies and gyms count as normal maps, and level sets whose mod has been removed are treated the same as the rest.

## Requirements

### MVP

| # | Requirement | Status |
|---|---|---|
| 1 | Show each level set's progress: done/total maps, status, deaths, time, berries | done |
| 2 | Show in-game titles for sets, maps and checkpoints (from `Dialog/English.txt`) | done (`--mods`) |
| 3 | Real map totals per set (from the mod zips' `Maps/` lists) | done. `-B`/`-C` files fold into their map, and `--set` shows each map's sides |
| 4 | Detail view of one set: every map, including not-opened ones | done (`--set`) |
| 5 | Checkpoints reached per map, and the saved room of the current session | done |
| 6 | Status per side (A/B/C): cleared, heart, deaths, time, checkpoints | todo. The script currently merges sides per map |
| 7 | Apply the completion rule above (all sides cleared + heart) | todo. Needs #6 and knowing which sides exist |
| 8 | Scan all slots in one run, and show the slot for each set | todo (`--all`) |
| 9 | Show the mod name users know (zip / `everest.yaml` name, e.g. `OmoriPack`) next to the set | todo |
| 10 | `--json` export of everything parsed, so the UI reads data instead of re-parsing saves | todo |
| 11 | Read-only: never write to save files, safe to run while the game is open | holds today, keep it |

### Should have

- Config file for the Saves and Mods paths (no more `--saves "/mnt/c/..."` each time)
- Extra stats already in the save: best time, best deaths, full clear, berries per side
- User fields beyond notes: difficulty, rating, "dropped" flag

### Later

- Aggregate the same mod across slots
- Checkpoint totals per side (e.g. "B side: checkpoint 11/14") and berry totals per map. Needs parsing the map `.bin`
- Dates (cleared on, last played). Not in the save (`LastSave` is always `0001-01-01`), so this needs snapshots between runs
- UI: start with a static HTML page generated from the `--json` output

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
- Windows saves: `C:\Program Files (x86)\Steam\steamapps\common\Celeste\Saves` (from WSL: `/mnt/c/...`). Mac: `~/Library/Application Support/Celeste/Saves`.

## Known issues

- None open. (Fixed: `--mods` used to count `-B.bin` / `-C.bin` as separate maps, 81 of 1,324 in my Mods folder.)

## Open questions

- Maps with no heart (e.g. some lobbies, vanilla Prologue/Epilogue) can never meet "cleared + heart". Treat "no heart exists" as satisfied? Knowing whether a map has a heart probably needs the `.bin`.
- Which vanilla chapters have B/C sides: hardcode the list.

## TODO

- See how players track progress manually in Excel sheets, to find which columns matter.
- Next build step: per-side status (#6, #7). `ModInfo.sides(sid)` already says which sides each map has.
- Mod name?