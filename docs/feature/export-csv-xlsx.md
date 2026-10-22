# Plan: export the progress table as CSV or Excel

Requested by the user (2026-10-16, TODO.md "Export as CSV or Excel"); plan written 2026-10-22, revised the same day (every mod, page only, no CLI). Not started.

## The request

- Export the table to a `.csv` or `.xlsx` file, to open in Excel or Google Sheets, from the page (and so the desktop app). No CLI flag.
- The player picks which columns to export; some are ticked by default.
- Row 1 is the header, then one row per mod (the page's top-level row). What's inside a mod (level sets, chapters, A/B/C sides) is left out.
- Every mod is exported, whatever the search box and Filter panel hide.
- The player picks the row order; by default it's the page's current sort (Time, highest first, unless they clicked another column).

## Design

### Where the rows come from

- The page sorts every mod with its own `SORTS` and `sortDir()` (`app.js`), skipping the search and filters, and posts `{fmt, slot, cols, ids}` to `POST /api/export`, `ids` in that order. One sort implementation, no Python copy to keep in step.
- `export.py` gets `to_rows(lib, slot, cols, ids) -> list[list]`: the header, then one row per mod ID, from the same view as the page (`all` = each mod's furthest slot, or one slot). No parsing and no completion rules here (DESIGN.md layers): it reads the model and `rules`' views. Unknown IDs or columns give 400.
- `to_csv(rows)` and `to_xlsx(rows)` write the file; the server answers with `Content-Disposition: attachment; filename="celeste-progress-2026-10-22.csv"`.

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

The ticked columns at first are the ones shown in the table right now (Columns menu), so the file matches what the player sees.

### Page

- An **Export** button in the toolbar opens a small panel (like Filter): format (CSV / Excel), the column checkboxes (same groups as the Columns menu, "From your saves" and "Yours"), Sort by (a select of the sort keys) and a direction toggle, both set to the page's current `state.sort` and `sortDir()`. Then **Download**, with "All N mods" next to it so it's clear filters don't apply.
- The panel's choices are kept in `/api/prefs` with the column settings.
- Desktop app: WebView2 and WKWebView don't reliably download from a link, so in the window the page asks `desktop.py` to save instead (pywebview's `SAVE_DIALOG`, then write the bytes). Check on both.

### File details

- **CSV:** standard library `csv`, UTF-8 with a BOM (Excel then shows accented mod names right), `\r\n` line ends. Cells starting with `=`, `+`, `-` or `@` (a note, a tag) get a leading `'`, so Excel doesn't run them as formulas.
- **xlsx:** see open questions: `openpyxl`, or the zip written by hand. Either way: bold header, frozen first row, an autofilter on the header, column widths from the longest value, numbers as numbers.

## Tests

- `to_rows` on the fixtures: header, one row per ID in the given order, the default columns, 400 on bad input.
- CSV: BOM, quoting of commas/quotes/newlines in notes, the formula guard.
- xlsx: read it back (with openpyxl, or unzip and parse `sheet1.xml`), check cell types and values.
- The page: playwright-cli on the fixtures, export with a filter on still gives every mod, in the page's sort.
- By hand: open both files in Excel and Google Sheets, from slot 1 on the Windows PC; the download in the desktop app on Windows and macOS.

## Build order

1. `to_rows` + CSV + `POST /api/export` + tests.
2. The Export panel; check with playwright-cli.
3. xlsx.
4. Desktop save dialog; Windows build.
5. README, NOTES.md, TODO.md (move to Done).

## Open questions

- **xlsx library.** `openpyxl` (pure Python, plus `et_xmlfile`; a few MB in the build) makes this a few lines and is well tested. Writing the zip by hand with `zipfile` keeps the standard-library-only rule (DESIGN.md "Tech stack", which gives no reason for it) but is ~100 lines of XML to maintain. Recommended: openpyxl, and update DESIGN.md, CLAUDE.md and the README's "Standard library only" line. Needs the user's OK.
- Are collabs one row (the mod) enough, or would players want a row per level set later?
- Exporting the player's fields alone (for moving to another PC, TODO.md) is a different feature: it needs an import too.
