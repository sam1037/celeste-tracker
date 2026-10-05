# celeste-tracker

See your Celeste mod progress straight from the save files, without enabling the mods (loading many mods slows the game down). Standard library only.

One row per **mod**, named the way you know it from Olympus (its GameBanana title), with collabs split into their level sets underneath. Progress is counted in **sides**: a chapter's A, B and C sides each count once, and a side is done when it's cleared and its heart is collected (or just cleared, for sides with no heart). By default all your save slots are combined: a side counts as done if you completed it in any slot, and deaths and time add up.

With `--mods` it reads your Mods folder (zip file lists, `everest.yaml` and `Dialog/English.txt` only) for each mod's chapters and sides and their in-game titles. Mod names come from Everest's public mod list (the same one Olympus uses), downloaded once a week and cached; nothing about your saves is sent. Without internet it uses the chapter's title, then the level set's title, then the mod's ID.

## Run

```bash
S="/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Saves"   # Windows saves, from WSL

uv run celeste_progress.py --saves "$S" --mods --save-config         # once: remember the folders
uv run celeste_progress.py --serve                                   # the page: open http://localhost:8765
uv run celeste_progress.py                                           # every mod, all slots combined
uv run celeste_progress.py --slot 1                                  # one slot, with its unfinished chapters
uv run celeste_progress.py --set "Sentient Forest"                   # one mod: its chapters and sides, per slot
uv run celeste_progress.py --note hikki "stopped at the ice part"
uv run celeste_progress.py --rate "Sentient Forest" 5             # also: --difficulty KEY TEXT, --drop / --undrop KEY
uv run celeste_progress.py --rename mindcrack "MINDCRACK"           # your own name for a mod ("" undoes it)
uv run celeste_progress.py --markdown progress.md
uv run celeste_progress.py --json progress.json                      # everything parsed, for other tools ('-' = stdout)
uv run celeste_progress.py --slot 1 --dump                           # raw XML outline, for debugging
```

`python -m celeste_tracker` works the same as `celeste_progress.py`.

`--serve [PORT]` starts a local page (only reachable from your own computer) with the same data: one row per mod with a progress bar, search, a slot picker, filters (unfinished, complete, dropped…) and sorting. Click a mod to open it: a collab opens to its level sets, each level set to its chapters, and a chapter to its A/B/C sides with each slot's result. Your rating, difficulty, dropped flag, name and note can be edited there too. The page reloads by itself when the game saves, and the URL keeps what you opened, so a view can be bookmarked.

`--save-config` stores `--saves` and `--mods` in a config file (`~/.local/share/celeste-tracker/config.toml` on Linux/WSL, `%APPDATA%\celeste-tracker\config.toml` on Windows). Later runs use it; flags still win, and `--no-mods` skips the Mods folder. The store (`tracker.db`: your notes and ratings, plus a cache of the Mods folder scan) and the mod list cache (`moddb.json`) sit next to it; `--offline` never downloads, `--refresh-moddb` downloads now. Without a config, the tool looks in the default Saves folder for your OS. Under WSL you need `--saves` or the config.

`--set` takes a mod's name or ID, a level set's ID or title, or a unique part of one; a collab's level set shows just that tier. `--note`, `--rate`, `--difficulty`, `--drop` and `--rename` take a mod's name or ID (or for notes and ratings, a level set or chapter), or a unique part of one. They are kept in `tracker.db` next to the config, and show in the Mine column and in `--set`. Notes from an old `celeste_notes.json` are imported on the first run (or with `--import-notes FILE`).

Statuses: a side is *completed*, *cleared, no heart*, *in progress* or *not opened*. A mod or level set is *complete*, *hearts missing* (everything cleared, some hearts not collected), *in progress*, *started*, *not started*, or *all opened done* when the mod isn't in the Mods folder to give the real totals (those totals are marked `?`). For mods, the tool can't yet tell whether a side has a heart at all, so a cleared side without one is never counted as done.

The tool only reads your saves and mods; it never writes to them.

## Develop

```bash
uv run pytest     # tests use made-up saves in tests/fixtures, never real ones
```

## Files

- `celeste_tracker/`: the code (layout in `doc/DESIGN.md`); `celeste_progress.py` is a thin entry point
- `tests/`: pytest tests and made-up fixture saves
- `doc/PRD.md`: goal, users, requirements and the definition of "completed"
- `doc/DESIGN.md`: tech stack and architecture
- `doc/NOTES.md`: build status, the save format and open questions
- `local/`: your own save copies for testing (gitignored)
