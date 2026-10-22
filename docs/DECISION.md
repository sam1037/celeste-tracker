# Decisions

Decisions about how the project is run, with why. Newest last. Design choices for the code itself are in [DESIGN.md](DESIGN.md) "Decisions".

## 1. Libraries are allowed (2026-10-22)

**Decision:** runtime code may use a third-party library when it saves real work. The standard library stays the first choice. Ask the user before adding one, and record it in DESIGN.md "Decisions".

**Why:** the old rule ("standard library only", except `pywebview`) had no written reason; it likely dates from the single script run with plain `python`. That no longer holds: players get a PyInstaller build with everything inside, and developers use `uv`, which installs dependencies itself. Keeping the rule would have meant writing an xlsx file by hand (~100 lines of zip and XML to maintain) instead of using `openpyxl`.

**Prefer:** pure-Python, well-maintained packages that PyInstaller bundles on Windows and macOS without extra steps. Unchanged: nothing from the player's files is sent anywhere, and the network use stays as PRD #12 says.

**First use:** `openpyxl` for the xlsx export ([features/export-csv-xlsx.md](features/export-csv-xlsx.md)).
