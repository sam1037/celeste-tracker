# celeste-tracker

A CLI that shows Celeste (Everest) mod progress straight from save files, without loading the mods. The code is the `celeste_tracker/` package laid out in `doc/DESIGN.md`; `celeste_progress.py` is a thin entry point.

Read the docs in `doc/` first:

- `doc/PRD.md`: the goal, users, use cases, the agreed definition of "completed", the requirements (MVP / should have / later), non-goals and open product questions.
- `doc/DESIGN.md`: tech stack, layers, package layout, data model, storage, testing and build order.
- `doc/NOTES.md`: done/todo status per requirement, the save and mod file format as verified on real saves, the known issues, open technical questions and the next build step.

## Run and test

```bash
S="/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Saves"   # the user's real Windows saves (WSL)
uv run celeste_progress.py --saves "$S" --slot 1 --mods     # slot 1: ~110 level sets, the big real test
uv run celeste_progress.py --saves "$S" --slot 31 --mods    # slot 31: small test slot the user plays to make test cases
uv run celeste_progress.py --file local/31.celeste          # an older copy of slot 31, works offline
uv run celeste_progress.py --saves "$S" --mods             # the default: all 32 slots combined, ~7 s
uv run pytest                                               # tests, on made-up saves in tests/fixtures
```

Testing the page (`--serve`): run the server on real saves with a scratch config, then render it with headless Windows Chrome and look at the PNG (Read shows images). Open views through the URL hash (`#q=…&open=<mod id>&sets=<mod id>/<level set>&ch=<chapter sid>`, several IDs joined by `%0A`).

```bash
SP=<scratchpad>; mkdir -p $SP/ui && cp ~/.local/share/celeste-tracker/moddb.json $SP/ui/
uv run celeste_progress.py --config $SP/ui/c.toml --saves "$S" --mods --offline --serve 8765   # in the background
W=$(wslpath -w $SP/ui)
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --no-first-run \
  --user-data-dir="$W\\chrome-profile" --window-size=1400,1000 --virtual-time-budget=8000 \
  --screenshot="$W\\shot.png" "http://localhost:8765/#q=sentient&open=Sentient%20Forest"
```

`--dump-dom` instead of `--screenshot` prints the rendered HTML. `--force-dark-mode` checks the dark theme. Chrome won't go narrower than ~500 px. Ignore its `LockFileEx` errors.

- Mods folder: `/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Mods` (~450 zips). `--mods` scans it in ~3 s.
- Verify changes by running against slot 1 and slot 31, not only mock files.
- The user has a config (`~/.local/share/celeste-tracker/config.toml`), so a bare `uv run celeste_progress.py` shows their real view. The first run of a week downloads the public mod list into `moddb.json` next to it; pass `--offline` to avoid that.
- In tests, pass `--offline` and a scratch `--config`: the mod list cache lives next to the config, and tests must never use the network.
- When testing `--note`, `--rate`, `--difficulty`, `--drop`, `--rename` or `--save-config` on real saves, pass `--config <scratch dir>/c.toml` plus `--saves "$S" --mods`: the store (`tracker.db`) sits next to the config, and the user's real store must not get test data.
- Test fixtures must be made up. Real saves never go in `tests/`; only `tests/fixtures/slots/*.celeste` is allowed past the `*.celeste` gitignore rule.
- The `VIRTUAL_ENV ... does not match` warning from uv comes from the user's shell and is harmless.

## Rules

- **Read-only:** never write to save files or the Mods folder.
- **No personal data in git:** `local/`, `*.celeste`, `Saves/`, `celeste_notes.json`, `tracker.db*` and `moddb.json` are gitignored, and must stay out of git.
- **Commit as you go:** make a commit after each finished change. Don't push without asking (no remote is set up yet).
- **Dependencies:** runtime code uses only the standard library until the desktop phase (then `pywebview`, see `doc/DESIGN.md`). `pytest` is the only dev dependency. Ask before adding anything else.
- **Follow the layers in `doc/DESIGN.md`:** front ends (CLI, web, desktop) never parse files themselves, and the completion rules live in one module.
- **Don't assume WSL:** other players will run this on Windows, so no hardcoded `/mnt/c` paths in the code.
- **Be honest about the data:** the save only stores internal IDs and opened maps, and has no dates. Say what is verified on real saves and what is inferred.
