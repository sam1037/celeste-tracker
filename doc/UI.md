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
| `--summit` | `#2f6fd0` | `#5b95e6` | accent: links, focus, the wordmark |
| `--progress` | `#2f6fd0` | `#5b95e6` | the progress bar, side chips and hearts: one color for every side |

Status isn't a color of its own: green "complete" and blue "in progress" are gone. Sides show their state by form (below).

This is the "Ice blue" palette, one hue on plain greys. The user found the first one (navy text, a lavender row tint, purple wordmark and blue bars) "not the best", compared four palettes on the same view (purple, green, blue, and the current one), and chose this one (2026-10-05).

**Type:** one family, **Atkinson Hyperlegible Next** (Braille Institute, SIL OFL; built for legibility, distinct without being showy). It ships with the page in `static/fonts/` (Latin and Latin Extended, ~53 KB, licence in `OFL.txt`), because the page must work offline and contact nothing (PRD #12); system fonts are the fallback for other scripts. Sizes: 20 px wordmark, 15 px mod names, 13 px table text, 12 px secondary text and column headers. Numbers use tabular figures and align right.

## Progress bar and side chips

Each mod and level set row has one bar, filled in the progress color by its share of sides cleared. Hovering over it lists the sides per letter ("B sides: 5 of 10 cleared"), from `by_side` in every view (DESIGN.md "JSON export"), so the page applies no rules.

The first version split the bar into A | B | C portions in the three heart colors. It read as a jumble when a later side was done before an earlier one (Dream to Awakening: B cleared, A not), so it went back to one bar in one color (2026-10-05).

Inside a mod, each side is a chip with its letter: **filled** = cleared, **outlined** = playing, **faint dashed** = not opened, with ♥ after it when the crystal heart was collected.

The player's own fields (rating, difficulty, dropped, rename, note) are hidden on the page for now, at the user's request (2026-10-05; `SHOW_EDITOR` in `app.js`). The CLI still edits them, and the tags column still shows what's set.

## Statuses

The page uses three statuses for a mod or level set, and the **Show** menu offers exactly those (plus All mods), each with its count, so the menu and the Status column use the same words (user, 2026-10-05):

| Page | Server status (`rules.py`, CLI, JSON) | Meaning |
|---|---|---|
| playing | in progress, started | opened, not every side cleared yet |
| ✓ complete | complete, all opened done | every side cleared |
| not started | not started | never opened |

- **"started" (opened, no side cleared) is shown as playing**, the same word an opened, uncleared side uses. Before, a mod could say "started" while its only side said "playing". The bar still shows 0 cleared.
- **"all opened done" is shown as complete.** It means the mod isn't in the Mods folder, so its real total is unknown and every side that was opened is cleared (2 mods in the author's saves). Its totals already carry a "?", and the status's tooltip says why.
- **Sides:** ✓ cleared, playing, not opened.
- Old bookmarks still work: `show=played` and `show=dropped` open All mods, `show=unfinished` opens Playing. The Dropped filter is gone while the page can't set the flag (the edit fields are hidden); dropped mods are still dimmed.
- Sorting by Status puts playing first, then complete, then not started; within one status, the mods closest to done come first.

## Layout

One table, Journal-style:

```
┌ Celeste Tracker   Sides cleared 485 of 1318   Mods complete 112 of 253          [Refresh] ┐
│ [search……………………………]  Slot [All ▾]  Show [Played ▾]                                     │
│ Resume: Sonder (A, room b-04) …   15 saved ▸                                               │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│   Mod ▾                    Sides                   Status    Deaths    Time      Slots      │
│ ▸ Celeste                  ██████████|█████|████  27/27  complete  4 210  123:04:32  32      │
│ ▸ Spring Collab 2020       ███████████████░░░░░  75/100  playing   9 817   48:45:48  1, 2    │
│   SpringCollab2020 ∙ 6 level sets                                                          │
│ ▾ Sentient Forest          ████|████|░░░░          2/3   playing   4 765   12:39:57  6       │
│     [A]♥ cleared  1 076 deaths  3:36:59  best 18:06  2 checkpoints                         │
│     [B]♥ cleared  3 369 deaths  8:39:10  best 21:04  3 checkpoints                         │
│     [C]  playing    320 deaths    23:46  slots 1, 2                                         │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **One surface** with a header row and alternating row backgrounds, not a separate card per mod.
- **At most 1200 px wide**, centered: the side margins grow on wide screens, so the name, the bar and the numbers stay close together.
- **Click a column header to sort** (it replaces the Sort menu), **click it again to flip the order.** A column starts in its natural order: names A to Z, numbers highest first, statuses playing first. Following the WAI-ARIA sortable table example, each sortable header is a button with `aria-sort`, a ↕ marks the columns you can sort by, and ▲ / ▼ shows the sorted one; the header gets a background on hover.
- **Pages of 50 mods**, with the pager at the bottom of the table, as in Carbon's data table: rows per page (25, 50, 100 or all), "101–150 of 253 mods", and previous / page numbers / next. A new search, slot or filter goes back to page 1; the page is in the URL. The pager only appears when there are more than 25 mods.
- **A Deaths column**, as in the Journal.
- **Sides only under the bar** ("75/100 sides"): the chapter count was the same as the side count for 239 of 272 mods, so it was dropped (user, 2026-10-05).
- **Opened rows expand in place**, under a thin indent line.
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

1. Font and tokens, side strips (with `by_side` from `rules.py`), side chips in heart colors, "playing". (done)
2. One table with a header row, sorting by column header, Deaths column, labeled totals in the top bar, the Olympus-style second line. (done; the Sort menu is gone, and "Slots and tags" sorts by the player's rating)
3. After the user's review (2026-10-05): one color for every side, the edit fields hidden, the Ice blue palette. (done)

Check each step with `playwright-cli` on the real saves (scratch config), light and dark.
