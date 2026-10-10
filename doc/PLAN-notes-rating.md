# Plan: your own notes, rating, difficulty and tags per mod, and one Filter panel

Branch `mod-notes-rating` (2026-10-10). Agreed with the user from three mockups, made-up mods on the page's real `style.css` (serve the repo root, e.g. `python3 -m http.server 8767`, and open `/doc/mockups/…`):

1. [notes-rating.html](mockups/notes-rating.html): the Rating column and the note on the mod's second line (A), against a Note column (B, rejected).
2. [your-fields.html](mockups/your-fields.html): the Yours panel, the grouped Columns menu, Difficulty and Tags columns.
3. [filter-and-edit.html](mockups/filter-and-edit.html): the Edit button on the hovered row, and the Filter panel with chips.

## The request

- Players type their own note for each mod, on the page. Notes are per mod, not per level set or chapter.
- A column to rate each mod by how much they enjoyed it, out of 5.
- Later more of the player's own columns: difficulty, custom tags.
- One place for filters, richer than the Show menu.
- The page must not get cluttered, and players must be able to find out they can edit a mod.

## What existed before

- The store (`tracker.db`, `user_fields`) has `note`, `difficulty` (free text), `rating` (1 to 5), `dropped` and `rename` per key, where a key can be a mod, a level set or a chapter.
- `POST /api/user` saves any of them; `app.js` had an editor for them, hidden since 2026-10-05 (`SHOW_EDITOR = false`).
- The CLI sets them: `--note`, `--rate`, `--difficulty`, `--drop`, `--rename`.
- The user's real store had no user fields (checked 2026-10-10), so nothing needs moving.

## Design

### Only per mod

- The page shows and edits the player's fields only on mods. The level set and chapter "note: …" lines go.
- `POST /api/user` refuses keys that aren't mod IDs (400).
- CLI: every edit flag takes only a mod, as `--rename` did (`resolve_key(..., mods_only=True)`). It keeps showing old level set and chapter notes ("Other notes"), so a store that has some doesn't lose them from view.

### Rating column

- **Rating**, between Time and Slot: the player's own marks go on the right, as Olympus puts its favorite heart. Header tooltip: "How much you enjoyed it, 1 to 5".
- Rated: the stars given in the accent, the rest as faint outlines. Not rated: empty, and five faint stars show while the row is hovered or focused.
- Click a star to rate; click the star you gave to clear it. Hovering previews the fill. The stars are a radio group (WAI-ARIA rating pattern): one Tab stop, arrow keys move. Clicking a star doesn't open the row.
- Sorts highest first; unrated mods last either way. The ★ tag on the second line goes.

### The note

- On the row: a mod's note takes the place of the dim second line (`✎ Stopped at the ice part…`), one line, cut off with "…", the whole note on hover. Mods with no note keep the ID line. Row height stays 58 px.
- Edited in the opened mod's Yours panel. Saved 600 ms after typing stops and when leaving the field; "Saved" shows for a moment, "Not saved: …" on an error. An empty field removes the note.
- Saving a note updates the page's own copy of the data instead of reloading, so typing is never interrupted; the live reload already waits while focus is in an edit field.
- The search matches notes.

### Finding out you can edit: the Edit button

- Hovering a mod row shows **✎ Edit** at the right end of the name, over a fade (as Gmail and Todoist show actions on the row under the mouse). It opens the mod and moves focus to its Yours panel. Tooltip: "Open to rate it, set a difficulty, tag it or write a note".
- Also: every opened mod shows its Yours panel, the help panel gets a "Your notes, ratings and tags" section, and the search placeholder mentions notes.

### The Yours panel

In an opened mod, under its facts, one compact panel with every field the player sets: Rating (stars), Difficulty (a menu), Tags (chips with ✕, "+ Add tag"), Note (a field that grows). Heading: "Yours", with "Only you see these. Your save files are never changed." Fields added later get a line here.

### Difficulty and tags

- **Difficulty** is a fixed list: Beginner, Intermediate, Advanced, Expert, Grandmaster (the community's collab tiers), or not set. The store refuses other values from now on; an old free-text value is still shown, and offered in the menu until changed.
- **Tags** are free words per mod (lowercase, trimmed, at most 30 characters, at most 20 per mod), in a new store table `user_tags (key, tag)`. Adding a tag suggests the player's existing tags.
- **Columns:** Difficulty and Tags, in the Columns menu's new "Yours" group (with Rating), start hidden. The first time the player sets a difficulty or adds a tag, that column turns on, with a one-time notice ("The Difficulty column is on now that you've set one." [Hide it] [OK]). Tags show as small chips, "+2" when they don't fit.

### The Filter panel

- A **Filter** button replaces the Show menu, with the number of filters on. Its panel has a line each for Status (in progress, completed, not started), Rating (★ 5, ★ 4 or more, ★ 3 or more, not rated), Difficulty (each tier, not set), Tags (each tag; a mod needs any or all of them) and Note (has a note, no note). Each choice shows how many mods it has in the slot shown.
- Choices in one line widen the list (OR), lines narrow it (AND). Rating's choices are one at a time.
- The filters on show as chips under the toolbar ("Status in progress, not started ✕"), with "Clear filters" and "3 of 253 mods".
- Kept in the URL hash (`st=`, `rate=`, `diff=`, `tag=`, `tagall=1`, `note=`); the old `show=` values still work and become a Status filter.
- **Slot** stays its own menu: it picks which slot's numbers are shown, it doesn't hide mods.
- The empty-table message says to clear the filters or the search.

### Rejected

- A Note column: empty on most rows, and its ~180 px come out of the Sides bar.
- Editing in the row itself (Notion, Linear): the clutter the user wants to avoid.
- A first-run tour: it gets in the way of a page opened every day.

## Build order

1. **Rating, notes, Yours panel, Edit button.** Server and CLI per mod only. The page's Rating column, note line, Yours panel (rating, note), Edit button, search by note, help.
2. **Filter panel.** Status, Rating, Note; chips; hash; replaces Show.
3. **Difficulty and tags.** Store (fixed difficulty list, `user_tags`), API, CLI (`--difficulty` from the list, `--tag` / `--untag`), the Yours panel lines, columns that turn on by themselves with the notice, filter lines.
4. Docs: UI.md, DESIGN.md, PRD.md, NOTES.md, README.

Each step: `uv run pytest`, then `playwright-cli` on slots 1 and 31 with a scratch config (so the real store gets no test data), light and dark; a commit per step. Last: a Windows desktop build, to check that edits survive closing the window.
