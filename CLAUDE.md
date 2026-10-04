# celeste-tracker

A CLI that shows Celeste (Everest) mod progress straight from save files, without loading the mods. Everything is in one file, `celeste_progress.py`, and it uses only the standard library.

Read `NOTES.md` first. It has the requirements (MVP / later, with done/todo status), the agreed definition of "completed", the save and mod file format as verified on real saves, the known issues, the open questions and the next build step.

## Run and test

```bash
S="/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Saves"   # the user's real Windows saves (WSL)
uv run celeste_progress.py --saves "$S" --slot 1 --mods     # slot 1: ~110 level sets, the big real test
uv run celeste_progress.py --saves "$S" --slot 31 --mods    # slot 31: small test slot the user plays to make test cases
uv run celeste_progress.py --file local/31.celeste          # an older copy of slot 31, works offline
```

- Mods folder: `/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Mods` (~450 zips). `--mods` scans it in ~3 s.
- Verify changes by running against slot 1 and slot 31, not only mock files.
- When testing `--note`, pass `--notes <scratch file>`. Otherwise it writes the user's real `celeste_notes.json`.
- The `VIRTUAL_ENV ... does not match` warning from uv comes from the user's shell and is harmless.

## Rules

- **Read-only:** never write to save files or the Mods folder.
- **No personal data in git:** `local/`, `*.celeste`, `Saves/` and `celeste_notes.json` are gitignored, and must stay out of git.
- **Commit as you go:** make a commit after each finished change. Don't push without asking (no remote is set up yet).
- **Keep it one stdlib-only script:** the code is grouped into `# ----` sections (locating files, mod data, XML helpers, parsing, notes, rendering, main). If it grows, split out a parsing module before starting a second script.
- **Be honest about the data:** the save only stores internal IDs and opened maps, and has no dates. Say what is verified on real saves and what is inferred.
