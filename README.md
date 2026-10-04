# celeste-tracker

See your Celeste mod progress straight from the save files, without enabling the mods (loading many mods slows the game down). Standard library only.

Progress is counted in **sides**: a map's A, B and C sides each count once. A side is done when it's cleared and its heart is collected (or just cleared, for sides with no heart). For each level set it shows sides and maps done out of total, status, mod name, deaths, time, berries and checkpoints reached, plus where you saved and quit. With `--mods` it also reads your Mods folder (zip file lists, `everest.yaml` and `Dialog/English.txt` only) for real map and side totals, mod names and in-game titles.

## Run

```bash
S="/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Saves"   # Windows saves, from WSL

uv run celeste_progress.py --saves "$S" --mods --save-config         # once: remember the folders
uv run celeste_progress.py --slot 1                                  # overview of a slot
uv run celeste_progress.py --all                                     # every slot, with a Slot column
uv run celeste_progress.py --slot 1 --set Expert                     # every map and side of one level set
uv run celeste_progress.py --slot 1 --note hikki "stopped at the ice part"
uv run celeste_progress.py --slot 1 --markdown progress.md
uv run celeste_progress.py --all --json progress.json                # everything parsed, for other tools ('-' = stdout)
uv run celeste_progress.py --slot 1 --dump                           # raw XML outline, for debugging
```

`python -m celeste_tracker` works the same as `celeste_progress.py`.

`--save-config` stores `--saves` and `--mods` in a config file (`~/.local/share/celeste-tracker/config.toml` on Linux/WSL, `%APPDATA%\celeste-tracker\config.toml` on Windows). Later runs use it; flags still win, and `--no-mods` skips the Mods folder. Without any of this, the tool looks in the default Saves folder for your OS. Under WSL you need `--saves` or the config.

`--set` takes a level set ID, its in-game title, its mod name, or a unique part of one. `--note` takes a level set or map ID, its title, or a unique part. Notes are stored in `celeste_notes.json` in the project folder.

Statuses: a side is *completed*, *cleared, no heart*, *in progress* or *not opened*. A level set is *complete*, *hearts missing* (everything cleared, some hearts not collected), *in progress*, *started*, or *all opened done* when there's no mod in the Mods folder to give the real totals (those totals are marked `?`). For mods, the tool can't yet tell whether a side has a heart at all, so a cleared side without one is never counted as done.

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
