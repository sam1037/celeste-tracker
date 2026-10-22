# Plan: export the progress table as CSV or Excel

Requested by the user (2026-10-16, TODO.md "Export as CSV or Excel"); plan written 2026-10-22. Not started.

## The request

- Export the table to a `.csv` or `.xlsx` file, to open in Excel or Google Sheets.
- The player picks which columns to export; some are ticked by default.
- Row 1 is the header, then one row per mod (the page's top-level row). What's inside a mod (level sets, chapters, A/B/C sides) is left out.
- The player picks the row order; by default it's the page's current sort (Time, highest first, unless they clicked another column).

## Design

### Where the rows come from

- `export.py` gets `to_rows(lib, slot, columns, sort, desc) -> list[list]`: the header, then one row per mod, from the same view as the page (`all` = each mod's furthest slot, or one slot). No parsing and no completion rules here (DESIGN.md layers): it reads the model and `rules`' views.
- The sort keys mirror `SORTS` in `app.js` (time, progress, name, author, deaths, rating, difficulty, slot, status), with the same rules: ties by name, mods without a rating/difficulty/author/slot last whichever way. One test checks the Python order against the page's order on the fixtures, so the two don't drift.
- `to_csv(rows)` and `to_xlsx(rows)` write the file. One implementation for the CLI and the page.

### Columns

| Column | Default | In the file |
|---|---|---|
| Mod | always | the name the page shows |
| Mod ID | | the zip's ID, for matching across exports |
| Author | ✓ | |
| Status | ✓ | completed / in progress / not started, the page's words |
| Sides cleared, Sides total | ✓ | two number columns, not "x/y", so a sheet can sum and divide |
| Deaths | ✓ | number |
| Time | ✓ | CSV: `h:mm:ss`; xlsx: a duration (number of days, `[h]:mm:ss` format) so it sorts and sums |
| Best, Berries | | as on the page (Best empty on multi-side mods) |
| Checkpoint | ✓ | name, room ID in brackets |
| Rating | ✓ | 1-5, empty if not rated |
| Difficulty, Tags | | tags joined with `; ` |
| Note | ✓ | the full text, newlines kept |
| Slot | ✓ (All slots) | the slot shown |

On the page, the ticked columns at first are the ones shown in the table right now (Columns menu), so the file matches what the player sees. The CLI uses the defaults above.

### Page

- An **Export** button in the toolbar opens a small panel (like Filter): format (CSV / Excel), the column checkboxes (same groups as the Columns menu, "From your saves" and "Yours"), Sort by (a select of the sort keys) and a direction toggle, both set to the page's current `state.sort` and `sortDir()`. Then **Download**.
- Download calls `GET /api/export?fmt=csv|xlsx&cols=…&sort=…&dir=…&slot=…`; the server answers with `Content-Disposition: attachment; filename="celeste-progress-2026-10-22.csv"`.
- Desktop app: WebView2 and WKWebView don't reliably download from a link, so in the window the page asks `desktop.py` to save instead (pywebview's `SAVE_DIALOG`, then write the bytes). Check on both.
- The panel's choices are kept in `/api/prefs` with the column settings.

### CLI

- `--csv FILE` and `--xlsx FILE` (`-` for stdout, CSV only), with `--columns author,deaths,time,…` and `--sort time` / `--sort -time` (minus = lowest first? or a `--asc` flag; pick one), next to `--markdown` and `--json`. Honors `--slot`.

### File details

- **CSV:** standard library `csv`, UTF-8 with a BOM (Excel then shows accented mod names right), `\r\n` line ends. Cells starting with `=`, `+`, `-` or `@` (a note, a tag) get a leading `'`, so Excel doesn't run them as formulas.
- **xlsx:** no openpyxl (CLAUDE.md: no new dependencies). Write the zip by hand with `zipfile`: `[Content_Types].xml`, `_rels/.rels`, `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, `xl/styles.xml`, `xl/worksheets/sheet1.xml`, with inline strings (no shared-strings table). Bold header, frozen first row, an autofilter on the header, column widths from the longest value, numbers as numbers. ~100 lines.

## Tests

- `to_rows` on the fixtures: header, one row per mod, the default columns, each sort key both ways, the "last whichever way" rules.
- CSV: BOM, quoting of commas/quotes/newlines in notes, the formula guard.
- xlsx: unzip it, parse `sheet1.xml`, check cell types and values; the zip opens in LibreOffice (`soffice --headless --convert-to csv`) if it's installed, skipped otherwise.
- `/api/export` returns the right type and filename; bad `cols` or `sort` give 400.
- By hand: open both files in Excel and Google Sheets, from slot 1 on the Windows PC; the download in the desktop app on Windows and macOS.

## Build order

1. `to_rows` + sorting + tests.
2. CSV writer and `--csv`.
3. xlsx writer and `--xlsx`.
4. `/api/export` and the Export panel; check with playwright-cli.
5. Desktop save dialog; Windows build.
6. README, NOTES.md, TODO.md (move to Done).

## Open questions

- Rows: every mod, or only the mods the page shows now (search and Filter applied)? Proposed: the ones shown, with an "All mods" checkbox; the page would send its filters, or the list of mod IDs.
- Are collabs one row (the mod) enough, or would players want a row per level set later?
- Export the player's fields alone (for moving to another PC, TODO.md) is a different feature: it needs an import too.
