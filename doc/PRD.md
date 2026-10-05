# Celeste mod progress tracker: PRD

## Goal

Help a player understand their progress on Celeste mods: which mods are completed or not, where they stopped, and stats per mod. Start as a CLI, then a desktop app.

## Users and problems

For now the user is one Celeste player (the author) with many Everest mods installed: a Mods folder of ~450 zips, and save slots with 100+ level sets. Later, other players with modded saves, most of them on Windows and not programmers.

- Loading many mods slows the game down, so most mods stay disabled. The game only shows progress for mods that are loaded, so there's no way to see progress on the rest without enabling them.
- Even with mods loaded, the game has no overview across mods: which ones are finished, which are half done, and where you stopped in each.
- The save only stores internal IDs (`Kever2025/Crispybag/Kever2025`), not the names players know. Even the mod's own ID in its zip (`SonderCrispy`) often isn't the name players saw when they downloaded it ("Sonder" on GameBanana).
- Players think in mods, but the game groups maps into level sets: one collab (Spring Collab 2020) is seven level sets.

## Terms

| Term | Meaning | Example |
|---|---|---|
| **Mod** | One download (one zip): a row in Olympus | Sentient Forest; The 2020 Celeste Spring Community Collab |
| **Level set** | A group of chapters shown together in chapter select (a folder under `Maps/`). Most mods have one; a collab has one per difficulty tier | `SpringCollab2020/1-Beginner` |
| **Chapter** (= **map**) | One playable level. "Map" is the modders' word (one `.bin` file), "chapter" the game's | Forest; Switchback Station |
| **Side** | The A, B or C version of a chapter, each its own `.bin` file | Forest B side |
| **Room** | One screen inside a side | `c-01` |
| **Checkpoint** | A room flagged as a checkpoint; the save lists the ones reached per side | `c-01` "Deep Woods" |

Mod > Level set > Chapter > Side > Room. The save has no record of rooms other than checkpoints reached and the room you saved in.

## Use cases

- Pick what to play next: see which mods are unfinished and how far along each one is.
- Get back into a mod after a break: see the last checkpoint reached and the saved room.
- Check how much of a collab is done as a whole, then per difficulty tier, down to which maps were never opened.
- See which B and C sides are left.
- Keep personal notes per mod or map (e.g. "stopped at the ice part").

## Definition of "completed"

The **side** is the main unit of progress, the way players count it: a map's B side is its own piece of work. Everything rolls up from sides: side → map → level set → mod.

A **mod** is one download (one zip). It can hold several **level sets**, the groups of chapters the game shows together in chapter select (a collab's difficulty tiers are level sets). The mod is what players recognize, so it is the top level everywhere.

**Rows are mods; the numbers count sides.** Each mod is one row, showing how many of its sides are done (e.g. Spring Collab 2020: 87/105 sides). Opening a row shows the progress underneath it.

- **Side completed:** cleared **and** its heart collected. A side that has no heart (e.g. some lobbies, vanilla Prologue/Epilogue) is completed once cleared.
- **Map completed:** every side the map has (A, plus B and C if they exist) is completed.
- **Level set completed:** every map in the set is completed.
- **Mod completed:** every level set in the mod is completed.
- **Sides are A, B and C.** Extra sides added by AltSidesHelper (e.g. `MtEverest-D`, a "D side") count as maps of their own, the way the save stores them.
- No special handling for now: lobbies and gyms count as normal maps, and level sets whose mod has been removed are treated the same as the rest.
- Clearing is yes/no for now. Levels of clearing (full clear, golden) are in Later.

## Requirements

Status for each requirement is tracked in [NOTES.md](NOTES.md#status).

### MVP

| # | Requirement |
|---|---|
| 1 | Show progress per mod, and per level set inside a mod that has several: sides done/total (the main number), maps done/total, status, deaths, time, berries |
| 2 | Show in-game titles for sets, maps and checkpoints |
| 3 | Real map and side totals per level set and per mod, counting maps the player has never opened |
| 4 | Detail view of one set: every map and each of its sides, including not-opened ones |
| 5 | Checkpoints reached per side, and the saved room of the current session |
| 6 | Status per side (A/B/C): cleared, heart, deaths, time, checkpoints |
| 7 | Apply the completion rules above (side, map, level set) |
| 8 | Scan all slots in one run, and show the slot for each mod |
| 9 | Name each mod the way players know it: its GameBanana title (e.g. "Sonder", not the zip's ID `SonderCrispy`). When that isn't available (offline, or the mod isn't on GameBanana): the map's title for a one-map mod, else the level set's title for a one-set mod, else the mod ID |
| 10 | Export everything parsed as JSON, so the UI reads data instead of re-parsing saves |
| 11 | Read-only: never write to save files, safe to run while the game is open |
| 12 | Works offline. The only network access is downloading Everest's public mod database (for #9), and nothing from the player's files is sent |

### Should have

- Config file for the Saves and Mods paths (no more `--saves "/mnt/c/..."` each time)
- Extra stats already in the save: best time, best deaths, berries per side
- User fields beyond notes: difficulty, rating, "dropped" flag
- Rename a mod, for GameBanana titles that read badly (e.g. "MINDCRACK C-Sides Update! MINDCRACK Map Pack")

### Later

- Aggregate the same mod across slots
- Levels of clearing per side: full clear (all berries), golden / deathless. The save has `FullClear`, and `BestDeaths` may cover deathless
- Checkpoint totals per side (e.g. "B side: checkpoint 11/14") and berry totals per map
- Dates (cleared on, last played)
- UI: a page in the browser first, then a desktop window. Like Olympus's mod list: one row per mod (GameBanana title, sides done/total, status). Opening a row drills down: level sets, then chapters, then sides. A level with only one entry is skipped, so a collab opens to its tiers and a one-chapter mod opens straight to its sides:
  ```
  ▸ The 2020 Celeste Spring Community Collab    87/105 sides   in progress
  ▾   ├ Beginner        19/19   complete
      ├ Expert           8/16   in progress
      │   ├ Switchback Station   A: in progress
      │   └ …
  ▾ Sentient Forest                               2/3 sides     in progress
      A  completed   287 deaths  1:01:07
      B  completed  1300 deaths  3:56:04
      C  in progress  288 deaths   20:35   checkpoint: Deep Woods
  ▸ Sonder                                        0/1 sides     started
  ```
- Ready for other players: a Windows download that runs without Python, WSL or a terminal, and finds the Celeste folder by itself

## Non-goals

- Changing save files or the Mods folder in any way (see #11).
- Installing, updating or enabling mods. Olympus does that.
- Speedrun timing or splits.
- Browsing or downloading mods from GameBanana.

## Success criteria

- For every level set in a real save, done/total and status match what the game shows when the mod is loaded.
- Every mod that is on GameBanana shows its GameBanana title.
- Running it is faster than starting the game with the mods enabled (today: ~3 s with `--mods` on ~450 zips).

## Open questions

- None open. (Decided: a side with no heart is completed once cleared; see the definition above.)
