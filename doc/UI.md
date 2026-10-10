# Celeste mod progress tracker: UI design

How the `--serve` page looks and why. What the tracker does is in [PRD.md](PRD.md); how the page is built (server, API, security) is in [DESIGN.md](DESIGN.md#ui---serve). Agreed with the user on 2026-10-05, from a plan written with the `frontend-design` skill (`.claude/skills/frontend-design`).

## Brief

- **Subject:** the player's Celeste progress across 250+ mods and 32 save slots.
- **Audience:** the author now, other players later. People who know Celeste's terms (sides, hearts, collabs, Olympus) and open the page between play sessions.
- **The page's one job:** pick what to play next, by seeing what's unfinished and how far along it is (PRD, first use case).
- **Treatment:** a practical tool for scanning every day: readable and dense, with one touch only Celeste has. Not a showcase.
- **Desktop only.** The page runs next to the game on a PC, so phone layouts aren't a target. The narrow-screen CSS that exists stays, but new work isn't designed for it.

## What players already know

- **The Journal** (in-game, in chapter select) is Celeste's own progress screen: one row per chapter, with columns for the A, B and C crystal hearts, strawberries, deaths and time. The tracker is the Journal for mods, so it borrows the Journal's columns, not its paper look.
- **Crystal heart colors:** in the game, A-side hearts are blue, B-side hearts red and C-side hearts gold. The page tried these as side colors in the bar and the chips, and the user found the three colors odd next to each other (2026-10-05), so every side now uses one progress color and the letter says which side.
- **Olympus**, the mod manager, lists one row per mod: the mod's title, then a dim second line (`ID version ∙ Filename.zip`), and on the right a favorite heart and an "Enabled" checkbox. Disabled (blacklisted) mods are shown at 50% opacity. (Read from `src/scenes/modlist.lua` in EverestAPI/Olympus, 2026-10-05.) The tracker's mod rows follow the same shape: title, dim ID line, the player's own marks on the right. Dropped mods are dimmed like disabled mods are in Olympus. The `∙` between the ID and the rest of the second line is Olympus's own convention, so that one line keeps it; everywhere else, figures get their own labels instead of dot-joined strings.

## Tokens

Defined once in `style.css` (`:root`, plus the dark values under `prefers-color-scheme: dark`).

| Token | Light | Dark | Role |
|---|---|---|---|
| `--snow` | `#f1f3f6` | `#12161e` | page background: plain cool grey |
| `--surface` | `#ffffff` | `#1a1f29` | the table and panels |
| `--surface-alt` | `#f7f8fa` | `#1f2531` | every second row |
| `--ink` | `#1a2130` | `#e4e8ef` | text (deep navy, not tinted black) |
| `--muted` | `#5b6578` | `#98a2b4` | secondary text |
| `--faint` | `#9ca3b1` | `#5b6475` | not started, not opened |
| `--line` | `#e0e4ea` | `#2a313d` | rules and borders |
| `--track` | `#e7eaf0` | `#29303c` | the empty part of a bar |
| `--guide` | `#c9cfd9` | `#3a4250` | the thread lines in an opened mod |
| `--hover` | `#e8f0fb` | `#1f2b3e` | the row under the mouse |
| `--summit` | `#2f6fd0` | `#5b95e6` | accent: links, focus, the wordmark |
| `--progress` | `#2f6fd0` | `#5b95e6` | the progress bars: one color for every side |

Status isn't a color of its own: green "complete" and blue "in progress" are gone. Sides show their state by form (below).

This is the "Ice blue" palette, one hue on plain greys. The user found the first one (navy text, a lavender row tint, purple wordmark and blue bars) "not the best", compared four palettes on the same view (purple, green, blue, and the current one), and chose this one (2026-10-05).

**Type:** one family, **Atkinson Hyperlegible Next** (Braille Institute, SIL OFL; built for legibility, distinct without being showy). It ships with the page in `static/fonts/` (Latin and Latin Extended, ~53 KB, licence in `OFL.txt`), because the page must work offline and contact nothing (PRD #12); system fonts are the fallback for other scripts. Sizes: 20 px wordmark, 15 px mod names, 13 px table text, 12 px secondary text and column headers. Numbers use tabular figures and align right.

## Progress bar

Every row has one bar with "x/y sides" under it, at every level: mod, level set, chapter and side (a side is 0/1 or 1/1). It's filled in the progress color by the share of sides cleared. Hovering over a mod's or level set's bar lists the sides per letter ("B sides: 5 of 10 cleared"), from `by_side` in every view (DESIGN.md "JSON export"), so the page applies no rules.

The first version split the bar into A | B | C portions in the three heart colors. It read as a jumble when a later side was done before an earlier one (Dream to Awakening: B cleared, A not), so it went back to one bar in one color (2026-10-05).

Until 2026-10-07, a chapter showed its sides as letter chips (filled = cleared, outlined = playing, dashed = not opened, ♥ after a collected heart), and an opened chapter showed a table of its sides with the checkpoints reached. The user asked for one form on every row instead: the bar and "x/y sides", no chips, no hearts in the table, no checkpoints for now. Hearts collected are still a figure on an opened mod. The chip is left only in "Where you left off", for the side being played.

The player's own fields were hidden on the page from 2026-10-05 until the Yours panel (below, "Your fields", 2026-10-10).

## Statuses

The page uses the same three statuses at every level (mod, level set, chapter, side), and the Status line of the **Filter** panel offers exactly those, each with its count, so the filter and the rows use the same words (user, 2026-10-07; before, mods said playing / complete and sides said cleared / playing / not opened):

| Page | Server status (`rules.py`, CLI, JSON) | Meaning |
|---|---|---|
| in progress | in progress, started | opened, not every side cleared yet |
| ✓ completed | complete, completed (chapters and sides), all opened done | every side cleared |
| not started | not started, not opened | never opened |

- **"started" (opened, no side cleared) is shown as in progress.** The bar still shows 0 cleared.
- **"all opened done" is shown as completed.** It means the mod isn't in the Mods folder, so its real total is unknown and every side that was opened is cleared (2 mods in the author's saves). Its totals already carry a "?", and the status's tooltip says why.
- The top bar says "Sides completed" and "Mods completed" to match.
- Old bookmarks still work: the status IDs stay `playing`, `complete` and `notstarted` (now `st=` in the URL), and an old `show=` becomes that Status filter; `show=played` and `show=dropped` open all mods, `show=unfinished` opens In progress. There's no Dropped filter (the page can't set the flag; the CLI can); dropped mods are still dimmed.
- The status is shown under the bar, at the right of "x/y sides", not in a column of its own (user, 2026-10-08): a full bar already said completed, so the column repeated it. Sorting by status (in progress first, then completed, then not started; within one status, closest to done first) is left only for old bookmarks (`sort=status`); the Sides header sorts by the share of sides cleared.

## Slots

In the all-slots view, a mod shows **one slot, its furthest** (`rules.py`, since `d0388fc`): every number on its row and under it comes from that slot. The row's tag says which one, "slot 1 (+5)" = slot 1, also played in 5 other slots (hover for their numbers). An opened mod says "Shown: slot 1, your furthest; also played in slot 2 (2/3 sides), …" instead of the old per-side lines ("cleared in slots 1, 2; playing in slot 8"), which described every slot while the numbers next to them came from one.

## Where you left off

The panel above the table lists every slot saved inside a chapter (Save & Quit), as a small table: slot, mod, chapter (when it isn't the mod's own name), side, last checkpoint, room, deaths this session, and that slot's sides on the mod. Clicking a row opens the mod, on whichever page has it.

- **Last checkpoint** is the last one the save lists for that side, by its in-game name (Wellness, Everglow); "start" when none was reached. The session's own start checkpoint is empty in all 15 sessions of the author's saves, so it isn't used.
- **The room** is the raw room ID (`ABuffZucchini_SmogCity_01`): the most exact place, but not a name players know, so it's a muted detail.
- The save has no dates, so rows are in slot order.

## Layout

One table, Journal-style:

```
┌ Celeste Tracker   Sides completed 486 of 1318   Mods completed 113 of 253              [Refresh] ┐
│ [search……………………………]  Slot [All ▾]  [Filter ▾]  [Columns ▾]                                     │
│ ▸ Where you left off   Save & Quit in 15 slots                                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│   Mod ↕                  Sides ↕                         Deaths ↕  Time ▼               Slots │
│ ▾ Spring Collab 2020     ███████░░ 75/100  in progress  12,953  48:45:42           45  slot 1 (+1)│
│     Mod ID … · Hearts collected 74 · Shown: slot 1, your furthest …                              │
│     ▸ Collab - Beginner  █████████ 19/19   ✓ completed   1,095   4:45:40           20            │
│     ▾ Collab - Expert    ████░░░░░  8/16   in progress   2,150   4:38:55            5            │
│         Starlit Grotto   █████████  1/1    ✓ completed     201     20:07   19:50    0            │
│ ▾ Sentient Forest        ██████░░░  2/3    in progress   1,875   5:17:51            9  slot 1 (+5)│
│       A side             █████████  1/1    ✓ completed     287   1:01:07   25:15    9            │
│       C side             ░░░░░░░░░  0/1    in progress     288     20:39       -    0            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **One surface** with a header row and alternating row backgrounds, not a separate card per mod.
- **At most 1200 px wide**, centered: the side margins grow on wide screens, so the name, the bar and the numbers stay close together.
- **Click a column header to sort** (it replaces the Sort menu), **click it again to flip the order.** A column starts in its natural order: names A to Z, numbers highest first. Following the WAI-ARIA sortable table example, each sortable header is a button with `aria-sort`, a ↕ marks the columns you can sort by, and ▲ / ▼ shows the sorted one; the header gets a background on hover.
- **Pages of 50 mods**, with the pager at the bottom of the table, as in Carbon's data table: rows per page (25, 50, 100 or all), "101–150 of 253 mods", and previous / page numbers / next. A new search, slot or filter goes back to page 1; the page is in the URL. The pager only appears when there are more than 25 mods.
- **A Deaths column**, as in the Journal.
- **Sides only under the bar** ("75/100 sides"): the chapter count was the same as the side count for 239 of 272 mods, so it was dropped (user, 2026-10-05).
- **A tree table** (the WAI-ARIA treegrid pattern; user's choice, 2026-10-07, over a list-and-detail view after comparing mockups of both on real data): an opened mod's level sets, chapters and sides are rows of the same table, on the mod row's columns, indented one step per level. Only rows with something under them open: a collab opens to its level sets, a level set to its chapters, and only a chapter with B or C sides opens, to "A side", "B side", "C side" rows. A chapter with one side (most mod chapters) has its numbers on its own row. A one-chapter mod opens straight to its sides. Before, each level was a box or table of its own with different columns, three levels of toggles deep.
- **Best and Berries columns:** Best is the best time of a single side, so it's filled on side rows and one-side chapters, and empty on rows that sum several sides. Both start hidden (user, 2026-10-08: Best was empty on every mod row, the main view); the Columns menu shows them.
- **Sticky rows** (user, 2026-10-08): while scrolling, the header row stays under the top bar, an opened mod's row under the header, and an opened level set's row under its mod, each only while the rows under it are on screen (as AG Grid's group rows and VS Code's sticky scroll do). A collab like Spring Collab opens to 100+ rows, and the column names and the mod you're in used to scroll away.
- **"Not loaded"** is a line in an opened mod's facts, not on the row: as a tag it was on most rows, and a faint ⊘ in its place confused the user (2026-10-08). It doesn't help pick what to play.
- **Thread lines inside an opened mod** (user, 2026-10-08), as in Reddit's comments: a thin line drops from each opened row's arrow (the mod's, a level set's, a chapter's) down its rows, one per level. Hovering a line lights all of it up; clicking it closes the row it comes from, and scrolls back to that row if it was off screen. Inside an opened mod there are no horizontal lines, not even under the mod's own row (tried and reverted, 2026-10-08): the thread lines group the rows. Tried first and rejected the same day: a tint behind the rows inside, and a thick blue line down the mod's left edge (it read as "selected" and sat away from the tree).
- **Hover:** every row, side rows included, gets the same background on hover, so the eye can follow it across to its numbers; only rows that open get the pointer cursor (2026-10-08). The hover color is `--hover`, a faint tint of the accent, since grey is already the color of every second mod.
- **Author column** (user, 2026-10-08), after the mod's name, sortable A to Z (mods with no author last either way), and the search matches it. It's the GameBanana author from the downloaded mod list (`moddb.json`): 261 of the 266 map mods in the author's Mods folder have one; a collab's is its team ("Spring Collab 2020 Team"). The other 5 aren't on GameBanana and show none. Local files were checked first (all 455 zips): only 1 `everest.yaml` has an `Author:` key; 23 collabs have per-map `<key>_author` dialog lines ("by ethanol"), some of which aren't authors ("Advanced (Easy)"); about 20 have free-text `credits.txt`. None of those gives a mod's author. Rows inside an opened mod have no author, so their name takes both columns.
- **Slot column** (user, 2026-10-08), at the right: the number of the slot the row shows (the mod's furthest), nothing else; the other slots it was played in are in the tooltip and the opened mod's facts. It replaced "Slots and tags" (`slot 0 (+31)` plus the player's tags), which was wide for what it said. It only shows with "All slots": in one slot it would say the same on every row. It sorts by slot number, mods not played last.
- **Columns** (user, 2026-10-08): a Columns menu in the toolbar shows or hides every column but Mod (Best and Berries start hidden; Reset columns goes back to that). Every column has a width in px except Sides, which takes what's left: a longer bar is more use than empty room after a name (a flexible Mod was too wide, user 2026-10-08). With Sides hidden, Mod takes what's left. Defaults: Mod 320 (fits "The 2020 Celeste Spring Community Collab"), Author 170, Deaths 64, Time 72, Slot 44 px. The grip on a column's left edge is the line between two columns: dragging it moves only that line, so the two columns change width in opposite directions and every other line stays put (the first version widened the column and moved everything left of it, which the user found odd); next to Sides, Sides gives or takes the width, never below 120 px. Double-clicking a line resets the two columns. The lines between column names always show, faint (1 px, `--guide`), so it's clear the columns can be resized (as in AG Grid and Excel; user, 2026-10-08), and turn 2 px blue under the mouse or while dragged. They're borders, not filled boxes: browsers round border widths to whole screen pixels, so on a 125% screen every line is equally thick (a 2 px box came out 2 or 3 pixels). The cursor is `ew-resize`: Chrome on Windows draws `col-resize` as a white bar, hard to see on the white header. The settings are kept in the store (`GET/POST /api/prefs`), not in the browser: the desktop window forgets its localStorage and gets a new port each run. No table library: the tree rows, thread lines and sticky rows are custom, a grid library would replace all of that and add a bundled file, and hiding and resizing took ~130 lines.
- **Your fields** (user, 2026-10-10; plan and mockups in [PLAN-notes-rating.md](PLAN-notes-rating.md)): the player's rating, difficulty, tags and note, all **per mod** (not per level set or chapter: the server and the CLI refuse those keys).
  - **Rating column**, between Time and Slot (the player's own marks on the right, as Olympus's favorite heart): five stars, the ones given in the accent and the rest as faint outlines. A mod not rated shows nothing until its row is hovered or focused, then faint stars to click (as iTunes' rating column); hovering a star previews up to it, clicking the star given clears it. A radio group (WAI-ARIA rating pattern): one Tab stop, arrow keys. Sorts highest first, mods not rated last.
  - **Note column** (user, 2026-10-11), in the Yours group, shown by default: the note in two lines at most, then "…", all of it on hover. Clicking a mod's Note cell opens the mod with the cursor in its note, so an empty cell is how to write one (text cursor, tooltip "Click to write a note"). The first version put the note on the mod's second line in place of the ID line, as Gmail shows a message's first words (2026-10-10); the user asked to try it as a column instead. The search matches notes and tags.
  - Tried and removed (user, 2026-10-11): a ✎ Edit button over the right end of the name on the hovered row, to show that a mod can be edited. It covered part of the name.
  - **The Yours panel** in every opened mod has all of them in one place (as Linear and Playnite keep an item's fields in its detail view): stars, a Difficulty menu, the tags as chips with ✕ and an "Add a tag" field (Enter or a comma adds; it suggests the player's other tags), and the note, a field that grows and saves 600 ms after typing stops and on leaving it. Saving doesn't redraw the page, so typing is never interrupted; the live reload waits while the cursor is in the panel. Its heading says the save files are never changed.
  - **Difficulty** is one of the collab tiers, Beginner, Intermediate, Advanced, Expert, Grandmaster (user, 2026-10-10: a fixed list for now); an old free-text value from the CLI still shows. **Tags** are the player's own words, lowercase, at most 30 characters and 20 per mod.
  - **Difficulty and Tags columns** start hidden, and turn on by themselves the first time the player sets a difficulty or adds a tag, once, with a notice that says so and offers to hide it again (as a new field becomes a column in GitHub Projects). With every column on, the widest give way on screen, Mod first, then Author, Note, Tags and Difficulty, down to their minimum, so the last column stays in view; Sides keeps at least 150 px, and its "x/y sides" line is cut off rather than run into Deaths.
  - Dropped and the rename are still set only with the CLI.
- **Filters** (user, 2026-10-10): one **Filter** button opens a panel in place of the Show menu, as Linear and Notion do: a line each for Status, Rating (5, 4 or more, 3 or more, not rated; one at a time), Difficulty, Tags (any or all of them) and Note, each choice a chip with how many mods it has in the slot shown. Choices on one line widen the list, lines narrow it. The filters on show as chips under the toolbar, with ✕, "Clear filters" and "3 of 273 mods"; the button shows how many lines are on. They're in the URL (`st`, `rate`, `diff`, `tag`, `tagall`, `note`). Slot stays a menu of its own: it picks which slot's numbers are shown, it doesn't hide mods.
- **Columns menu** in two groups, "From your saves" and "Yours" (Rating, Difficulty, Tags). The page saves which columns it knew, so a column added later starts as its default says even for a player with saved settings.
- **Help** (user, 2026-10-08; ideas compared in NOTES.md "Page help"): a ? button at the right of the top bar, and the ? key (as on GitHub and Gmail), open a help panel, a native `<dialog>`: how to read a row (the bar, x/y sides, the three statuses, the "?" after a total), what the Slot column means, how to open, sort, hide and resize, the keys, and that the page follows the game's saves while Refresh rereads the Mods folder. Escape, the ✕ or a click outside closes it. No first-open tour: it would get in the way of a page opened every day. The text is static in `index.html`; change it with the page.
- **Column names sit at the left of their column**, next to the line before them, numbers included (user, 2026-10-11: some names hugged the line on their left and others the one on their right). The numbers under them stay right-aligned.
- **Row height:** every mod row is the same height (58 px), with room for the second line whether a mod has one or not (user, 2026-10-08).
- **`/` focuses the search**, as on GitHub and YouTube, unless you're typing in a field already.
- An opened mod first shows one line of facts: mod ID, GameBanana title, hearts collected and the slot shown.
- Text is left-aligned, numbers right-aligned, and the bars share one column edge.
- Rejected: a grid of postcard tiles like chapter select. It looks good at first, but 253 tiles are slow to scan and can't be sorted like columns.

## Principles

1. **Scan first, read second:** a row answers "how done is this?" at a glance, through the bar.
2. **Celeste's own words:** sides, hearts, checkpoints, and the statuses below.
3. **Form carries state:** fill, outline and dash say how far a side is, in one color; the letter says which side.
4. **Motion only answers the player:** a row may expand smoothly when opened. No entrance animations.
5. **Each figure gets its own label**, not a dot-joined string (the Olympus ID line is the one exception, above).

## Rejected while planning

Checked against the `frontend-design` skill's list of generic defaults:

- The Journal's paper and handwriting look: cream paper is the most common AI-made look. Kept the Journal's columns and heart colors instead.
- A big stat banner as the opener: the totals are labeled figures in the top bar, and the table comes first.
- A pixel-art font for the wordmark: a second flourish next to the bars.
- Green for "complete" next to blue for "in progress": form carries status instead.

## Build order

1. Font and tokens, side strips (with `by_side` from `rules.py`), side chips in heart colors, "playing". (done; chips and "playing" since replaced, see 4)
2. One table with a header row, sorting by column header, Deaths column, labeled totals in the top bar, the Olympus-style second line. (done; the Sort menu is gone, "Slots and tags" sorted by the player's rating until it became Slot, see 6)
3. After the user's review (2026-10-05): one color for every side, the edit fields hidden, the Ice blue palette. (done)
4. After the user's review (2026-10-07): the tree table, a bar and "x/y sides" on every row instead of chips and hearts, Best and Berries columns, the statuses not started / in progress / completed at every level. (done)
5. After the user's review (2026-10-08): sticky header, mod and level set rows; the status under the bar instead of a Status column; Best and Berries hidden; "not loaded" moved to the opened mod's facts; `/` for the search; thread lines that close their row, as on Reddit. (done)
6. After the user's review (2026-10-08): the Author column; Slot instead of "Slots and tags"; the Columns menu, column resizing; the same height for every mod row; the help panel. (done)
7. The player's fields on the page (2026-10-10, revised 2026-10-11): the Rating column, the Note column, the Yours panel, difficulty and tags with their columns, and the Filter panel instead of Show. (done)

Check each step with `playwright-cli` on the real saves (scratch config), light and dark.
