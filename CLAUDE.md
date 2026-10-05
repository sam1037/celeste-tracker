# celeste-tracker

A CLI that shows Celeste (Everest) mod progress straight from save files, without loading the mods. The code is the `celeste_tracker/` package laid out in `doc/DESIGN.md`; `celeste_progress.py` is a thin entry point.

Read the docs in `doc/` first:

- `doc/PRD.md`: the goal, users, use cases, the agreed definition of "completed", the requirements (MVP / should have / later), non-goals and open product questions.
- `doc/DESIGN.md`: tech stack, layers, package layout, data model, storage, testing and build order.
- `doc/NOTES.md`: done/todo status per requirement, the save and mod file format as verified on real saves, the known issues, open technical questions and the next build step.

## Run and test

The user works on this project from two machines: WSL on the Windows PC that has the game, and a Mac. The real saves, the Mods folder and `local/` (gitignored) are only on the Windows PC. On the Mac, run `uv run pytest` and the page on the test fixtures, and say that the change still needs checking on the real saves on the Windows PC. Check which machine you're on (`uname`) before using the paths below.

```bash
S="/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Saves"   # the user's real Windows saves (WSL only)
uv run celeste_progress.py --saves "$S" --slot 1 --mods     # slot 1: ~110 level sets, the big real test
uv run celeste_progress.py --saves "$S" --slot 31 --mods    # slot 31: small test slot the user plays to make test cases
uv run celeste_progress.py --file local/31.celeste          # an older copy of slot 31, works offline
uv run celeste_progress.py --saves "$S" --mods             # the default: all 32 slots combined, ~1.2 s
uv run pytest                                               # tests, on made-up saves in tests/fixtures
```

Testing the page (`--serve`): run the server with a scratch config (on real saves on the Windows PC, on `tests/fixtures/slots` on the Mac), then drive it with `playwright-cli` (the skill in `.claude/skills/playwright-cli`, works on both machines). It reads the page as an element tree with refs, clicks and types, reads the console, and takes screenshots (Read shows images). Open views through the URL hash (`#q=…&open=<mod id>&sets=<mod id>/<level set>&ch=<chapter sid>`, several IDs joined by `%0A`).

- Run `playwright-cli` from the repo root: `.playwright/cli.config.json` there makes it use Playwright's Chromium. From anywhere else it looks for Google Chrome, which WSL doesn't have.
- Its snapshots and logs go to `.playwright-cli/` (gitignored, since they show the user's mods and times). Delete it when done, and `playwright-cli close` the browser.
- Setup on a new machine (needs Node): `npm install -g @playwright/cli@latest`, then `playwright-cli install-browser chromium`.

```bash
SP=<scratchpad>; mkdir -p $SP/ui && cp ~/.local/share/celeste-tracker/moddb.json $SP/ui/   # Mac: ~/Library/Application Support/celeste-tracker/
uv run celeste_progress.py --config $SP/ui/c.toml --saves "$S" --mods --offline --serve 8765   # in the background; Mac: --saves tests/fixtures/slots, no --mods
playwright-cli open "http://localhost:8765/#q=sentient"
playwright-cli find "Sentient Forest"                      # the matching part of the element tree, with refs like f1e22
playwright-cli click f1e22                                 # open the row
playwright-cli screenshot --filename=$SP/ui/shot.png       # then Read the PNG
playwright-cli console                                     # JS errors
playwright-cli close
```

On WSL, headless Windows Chrome also works for a quick one-shot screenshot, with no setup:

```bash
W=$(wslpath -w $SP/ui)
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --no-first-run \
  --user-data-dir="$W\\chrome-profile" --window-size=1400,1000 --virtual-time-budget=8000 \
  --screenshot="$W\\shot.png" "http://localhost:8765/#q=sentient&open=Sentient%20Forest"
```

`--dump-dom` instead of `--screenshot` prints the rendered HTML. `--force-dark-mode` checks the dark theme. Chrome won't go narrower than ~500 px. Ignore its `LockFileEx` errors.

- Mods folder (WSL): `/mnt/c/Program Files (x86)/Steam/steamapps/common/Celeste/Mods` (~450 zips). `--mods` scans it in ~3 s the first time, then ~0.1 s: unchanged zips come from the cache in `tracker.db`.
- Verify changes by running against slot 1 and slot 31, not only mock files.
- On the Windows PC the user has a config (`~/.local/share/celeste-tracker/config.toml` in WSL), so a bare `uv run celeste_progress.py` shows their real view. The first run of a week downloads the public mod list into `moddb.json` next to it; pass `--offline` to avoid that.
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
