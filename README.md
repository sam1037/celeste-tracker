# celeste-tracker

See your Celeste mod progress straight from the save files, without enabling the mods (loading many mods slows the game down). Standard library only.

It reads one save slot (`N.celeste`) and shows, per level set: maps done out of total, status, deaths, time, berries and checkpoints reached, plus where you saved and quit. With `--mods` it also reads your Mods folder (zip file lists and `Dialog/English.txt` only) for real map totals and in-game titles.

## Run

```bash
S="/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Saves"   # Windows saves, from WSL

uv run celeste_progress.py --saves "$S" --slot 1 --mods                # overview of a slot
uv run celeste_progress.py --saves "$S" --slot 1 --mods --set Expert   # every map of one level set
uv run celeste_progress.py --saves "$S" --slot 1 --mods --note hikki "stopped at the ice part"
uv run celeste_progress.py --saves "$S" --slot 1 --mods --markdown progress.md
uv run celeste_progress.py --saves "$S" --slot 1 --dump                # raw XML outline, for debugging
```

`--set` and `--note` take a level set or map ID, its in-game title, or a unique part of either. Notes are stored in `celeste_notes.json` next to the script.

Without `--saves`, the script looks in the default Saves folder for your OS (Windows, macOS, Linux). Under WSL you need `--saves`.

The script only reads files; it never writes to your saves.

## Files

- `celeste_progress.py`: the tracker
- `doc/PRD.md`: goal, users, requirements and the definition of "completed"
- `doc/DESIGN.md`: tech stack and architecture
- `doc/NOTES.md`: build status, the save format and open questions
- `local/`: your own save copies for testing (gitignored)
