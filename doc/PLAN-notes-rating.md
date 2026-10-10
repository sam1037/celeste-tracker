# Plan: notes and an enjoyment rating per mod, edited on the page

Branch `mod-notes-rating` (2026-10-10). Mockup: [mockups/notes-rating.html](mockups/notes-rating.html), made-up mods on the page's real `style.css` (serve the repo root, e.g. `python3 -m http.server 8767`, and open `/doc/mockups/notes-rating.html`).

## The request

- Players type their own note for each mod, on the page.
- Notes are per mod only, not per level set or chapter.
- A column to rate each mod by how much they enjoyed it, out of 5.
- The page must not get cluttered.

## What exists already

- The store (`tracker.db`, `user_fields`) already has `note` and `rating` (1 to 5) per key, and the key can be a mod, a level set or a chapter. No schema change is needed.
- `POST /api/user` already saves any field, and `app.js` has a save path that isn't used: `mineEditor`, hidden behind `SHOW_EDITOR = false` since 2026-10-05.
- The CLI sets both: `--note KEY TEXT` and `--rate KEY N` (mod, level set or chapter).
- Today the page shows a rating only as a ★★★ tag on the mod's second line, level set and chapter notes as "note: …" under their names, and mod notes nowhere.
- The user's real store has no notes or ratings yet (checked 2026-10-10), so nothing needs moving.

## Design (variant A in the mockup)

### Rating column

- A **Rating** column with five stars, between Time and Slot. The player's own marks go on the right, as Olympus puts its favorite heart (UI.md "What players already know"). The header's tooltip says "How much you enjoyed it, 1 to 5".
- **Rated:** the stars given are filled in the accent (`--summit`), and the rest are faint outlines (`--guide`), so "3 of 5" reads as a scale.
- **Not rated:** the cell is empty. Hovering the row or tabbing into it shows five faint stars to click. Most of the ~250 rows will have no rating, so empty cells keep the table quiet.
- **Click a star to rate.** Clicking the star you already gave clears the rating, as the hidden editor did. Hovering previews the fill up to that star. Each star is a button ("3 of 5") with `aria-pressed`, so it works from the keyboard. Clicks on a star don't open the row.
- **Sorting:** click the header for highest first; unrated mods go last either way. The `rating` sort and `sort=rating` bookmarks already exist.
- About 84 px wide, in the Columns menu like the others, and shown by default. Existing players' saved settings don't list it as hidden, so it shows for them too.
- The ★ tag on the second line goes, since the column replaces it. The difficulty and "dropped" tags stay, as the CLI still sets them.

### Notes

- **On the row:** when a mod has a note, the note takes the place of the dim second line (`✎ Stopped at the ice part…`), on one line and cut off with "…". Hovering shows the whole note. The row height stays 58 px. Mods with no note keep the ID line as today. The mod ID stays in the opened mod's facts.
- **Editing:** an opened mod gets a **Note** field under its facts, one line that grows as you type, up to ~6 lines. It saves 600 ms after you stop typing and when you leave the field, then shows "Saved" for a moment. If saving fails it says "Not saved", with the server's error. Emptying the field removes the note.
- **No editing on the row itself:** a field in every row would be the clutter we want to avoid. Opening the mod is one click.
- **Search matches notes**, so "ice part" finds the mod. The search placeholder and the help panel say so.
- **The live reload waits while you type:** it already skips reloading while focus is in the editor (`.mine`); the note field joins that check.

### Notes and ratings only per mod

- The page stops showing level set and chapter notes and ratings. There are none in the real store.
- `POST /api/user` refuses `note` and `rating` for keys that aren't mod IDs (400). The page only sends mod IDs anyway; this keeps the rule in one place.
- CLI: `--note` and `--rate` take only a mod, like `--rename` (`resolve_key(..., mods_only=True)`). A level set or chapter name gets "No mod matches …". The CLI keeps showing old level set and chapter notes (in "Other notes"), so a store that has some doesn't lose them from view.

### Rejected (variant B in the mockup)

A **Note column:** most mods have no note, so the column would be empty on most rows. It needs ~180 px, taken from the Sides bar (the column that matters most), and still cuts off every real note.

Also rejected: a note icon with a tooltip (it hides the text the player wrote to see), and a popover editor on the row (more code, for something opening the mod already gives).

## Changes, file by file

| File | Change |
|---|---|
| `web/static/app.js` | `COLUMNS` gets `rating` (sort `rating`, 84 px). `cells()` gets a star cell, and the star click handler moves from `.mine` to the row. `modCard`: note on the second line, no ★ tag. `modBody`: the note field instead of `mineEditor`, which goes, along with `SHOW_EDITOR`. The note leaves the `sub` of level set and chapter rows. The search matches `m.user.note`. Debounced save, "Saved" or "Not saved". The typing guard also checks `.note-edit`. Unrated mods sort last. |
| `web/static/style.css` | `.rate` (stars), `.sub.note`, `.note-edit`; the `.mine` and `.stars` rules go. |
| `web/static/index.html` | The search placeholder mentions notes. Help: a "Your notes and ratings" section, and the Rating column in "The table". |
| `web/server.py` | `App.edit`: `note` and `rating` only for mod IDs. |
| `cli.py` | `--note` and `--rate` resolve mods only; their help text says "a mod". |
| `tests/test_server.py` | Saving a note and a rating on a mod works; on a chapter key it's a 400. |
| `tests/test_cli.py` | `--note` on a chapter is refused; `test_note` (which notes the chapter "Forest") moves to a mod. |
| `doc/UI.md`, `PRD.md`, `DESIGN.md`, `NOTES.md` | UI.md: the Rating column and notes, in Layout and the build order; the paragraph about hidden edit fields changes. PRD: "notes per mod or map" becomes per mod. DESIGN: `user_fields` keys for note and rating. NOTES: status. |
| `README.md` | The `--serve` paragraph mentions notes and the rating. |

`rules.py`, `model.py` and `store.py` don't change: the fields are already in the model and the JSON (`m.user`).

## Build order

1. Server and CLI: mod-only notes and ratings, with tests.
2. Page: the Rating column (show, click, clear, sort, Columns menu).
3. Page: the note on the second line, the note field in an opened mod, saving, search.
4. Help panel, docs, README.
5. Check with `playwright-cli` on slots 1 and 31 (scratch config, so the real store gets no test data), in light and dark: rate, clear, sort, type a note, reload, search for it, live reload while typing. Then a Windows desktop build: a note and a rating survive closing and reopening the window.

## Questions for the user

1. **Column name:** "Rating", "Fun" or "Enjoyment"? The plan uses "Rating" with a tooltip, since the field is called rating everywhere else.
2. **The second line:** should a note replace the ID line (as planned), or follow it ("GlacierPass ∙ ✎ Stopped at…")? Following it keeps the Olympus look but leaves the note less room.
3. **Difficulty, dropped and rename:** keep them CLI-only for now (as planned), or add them to the opened mod later?
