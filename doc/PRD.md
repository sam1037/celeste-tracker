# Celeste mod progress tracker: PRD

## Goal

Help a player understand their progress on Celeste mods: which mods are completed or not, where they stopped, and stats per mod. Start as a CLI (`celeste_progress.py`), add a UI later.

## Users and problems

The user is a Celeste player with many Everest mods installed: a Mods folder of ~450 zips, and save slots with 100+ level sets.

- Loading many mods slows the game down, so most mods stay disabled. The game only shows progress for mods that are loaded, so there's no way to see progress on the rest without enabling them.
- Even with mods loaded, the game has no overview across mods: which ones are finished, which are half done, and where you stopped in each.
- The save only stores internal IDs (`NotPhobos/Omori/Snow Mountain`), not the names players know from the game (`The Hikkikomori Route`) or from the mod list (`OmoriPack`).

## Use cases

- Pick what to play next: see which mods are unfinished and how far along each one is.
- Get back into a mod after a break: see the last checkpoint reached and the saved room.
- Check how much of a collab is done, down to which maps were never opened.
- See which B and C sides are left.
- Keep personal notes per mod or map ("stopped at the ice part").

## Definition of "completed"

- **Map completed:** every side the map has (A, plus B and C if they exist) is cleared **and** has its heart.
- **Level set completed:** every map in the set is completed.
- No special handling for now: lobbies and gyms count as normal maps, and level sets whose mod has been removed are treated the same as the rest.

## Requirements

Status for each requirement is tracked in [NOTES.md](NOTES.md#status).

### MVP

| # | Requirement |
|---|---|
| 1 | Show each level set's progress: done/total maps, status, deaths, time, berries |
| 2 | Show in-game titles for sets, maps and checkpoints |
| 3 | Real map totals per set, counting maps the player has never opened |
| 4 | Detail view of one set: every map, including not-opened ones |
| 5 | Checkpoints reached per map, and the saved room of the current session |
| 6 | Status per side (A/B/C): cleared, heart, deaths, time, checkpoints |
| 7 | Apply the completion rule above (all sides cleared + heart) |
| 8 | Scan all slots in one run, and show the slot for each set |
| 9 | Show the mod name users know (e.g. `OmoriPack`) next to the set |
| 10 | Export everything parsed as JSON, so the UI reads data instead of re-parsing saves |
| 11 | Read-only: never write to save files, safe to run while the game is open |

### Should have

- Config file for the Saves and Mods paths (no more `--saves "/mnt/c/..."` each time)
- Extra stats already in the save: best time, best deaths, full clear, berries per side
- User fields beyond notes: difficulty, rating, "dropped" flag

### Later

- Aggregate the same mod across slots
- Checkpoint totals per side (e.g. "B side: checkpoint 11/14") and berry totals per map
- Dates (cleared on, last played)
- UI: start with a static HTML page generated from the JSON export

## Non-goals

- Changing save files or the Mods folder in any way (see #11).
- Installing, updating or enabling mods. Olympus does that.
- Speedrun timing or splits.

## Success criteria

- For every level set in a real save, done/total and status match what the game shows when the mod is loaded.
- Running it is faster than starting the game with the mods enabled (today: ~3 s with `--mods` on ~450 zips).

## Open questions

- Maps with no heart (e.g. some lobbies, vanilla Prologue/Epilogue) can never meet "cleared + heart". Treat "no heart exists" as satisfied?
