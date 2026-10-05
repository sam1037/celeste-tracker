# Celeste mod progress tracker: UI design

How the `--serve` page looks and why. What the tracker does is in [PRD.md](PRD.md); how the page is built (server, API, security) is in [DESIGN.md](DESIGN.md#ui---serve). Agreed with the user on 2026-10-05, from a plan written with the `frontend-design` skill (`.claude/skills/frontend-design`).

## Brief

- **Subject:** the player's Celeste progress across 250+ mods and 32 save slots.
- **Audience:** the author now, other players later. People who know Celeste's terms (sides, hearts, collabs, Olympus) and open the page between play sessions.
- **The page's one job:** pick what to play next, by seeing what's unfinished and how far along it is (PRD, first use case).
- **Treatment:** a practical tool for scanning every day: readable and dense, with one touch only Celeste has. Not a showcase.
- **Desktop only.** The page runs next to the game on a PC, so phone layouts aren't a target. The narrow-screen CSS that exists stays, but new work isn't designed for it.

## What players already know

- **The Journal** (in-game, in chapter select) is Celeste's own progress screen: one row per chapter, with columns for the A, B and C crystal hearts, strawberries, deaths and time. The tracker is the Journal for mods, so it borrows the Journal's columns and side colors, not its paper look.
- **Crystal heart colors:** in the game, A-side hearts are blue, B-side hearts red and C-side hearts gold. The page uses these to tell sides apart (adapted for contrast in both themes).
- **Olympus**, the mod manager, lists one row per mod: the mod's title, then a dim second line (`ID version ∙ Filename.zip`), and on the right a favorite heart and an "Enabled" checkbox. Disabled (blacklisted) mods are shown at 50% opacity. (Read from `src/scenes/modlist.lua` in EverestAPI/Olympus, 2026-10-05.) The tracker's mod rows follow the same shape: title, dim ID line, the player's own marks on the right. Dropped mods are dimmed like disabled mods are in Olympus. The `∙` between the ID and the rest of the second line is Olympus's own convention, so that one line keeps it; everywhere else, figures get their own labels instead of dot-joined strings.

## Tokens

Defined once in `style.css` (`:root`, plus the dark values under `prefers-color-scheme: dark`).

| Token | Light | Dark | Role |
|---|---|---|---|
| `--snow` | `#eef1f6` | `#141822` | page background, cool like snow on the mountain |
| `--surface` | `#ffffff` | `#1c2130` | the table and panels |
| `--surface-alt` | `#f5f3fa` | `#222738` | every second row |
| `--ink` | `#1b2233` | `#e6e9f2` | text (deep navy, not tinted black) |
| `--muted` | `#5d6780` | `#9aa3b8` | secondary text |
| `--line` | `#dde2ec` | `#2d3346` | rules and borders |
| `--summit` | `#6a4bb0` | `#a98be6` | accent: links, focus, the wordmark (the purple the page already had) |
| `--heart-a` | `#3c7fd4` | `#6ea5ec` | A sides |
| `--heart-b` | `#d23a52` | `#ec6a7e` | B sides |
| `--heart-c` | `#c9961a` | `#e3b548` | C sides |

Status isn't a color of its own: green "complete" and blue "in progress" are gone. Sides show their state by form (below), and the three heart colors only say which side it is.

**Type:** one family, **Atkinson Hyperlegible Next** (Braille Institute, SIL OFL; built for legibility, distinct without being showy). It ships with the page in `static/fonts/` (Latin and Latin Extended, ~53 KB, licence in `OFL.txt`), because the page must work offline and contact nothing (PRD #12); system fonts are the fallback for other scripts. Sizes: 20 px wordmark, 15 px mod names, 13 px table text, 12 px secondary text and column headers. Numbers use tabular figures and align right.

## The side strip

The one bold element. Each mod and level set row shows its progress as a strip in **A | B | C portions**, each as wide as that side's share of the mod's sides, filled in its heart color as sides are cleared:

```
Spring Collab 2020    ████████████████░░░░░                  75/100   (A sides only)
Sentient Forest       ███████|███████|░░░░░░░                  2/3
                         A       B      C
Glyph                 ██████████████████|███                   7/7
```

It answers the PRD use case "see which B and C sides are left" from the list, without opening anything. The counts come from the server (`by_side` in every view, see DESIGN.md "JSON export"): the page applies no rules.

Inside a mod, each side is a chip in its heart color: **filled** = cleared, **outlined** = playing, **faint dashed** = not opened, with ♥ after it when the crystal heart was collected.

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
- **Click a column header to sort** (it replaces the Sort menu).
- **A Deaths column**, as in the Journal.
- **Opened rows expand in place**, under a thin indent line.
- Text is left-aligned, numbers right-aligned, and the strips share one column edge.
- Rejected: a grid of postcard tiles like chapter select. It looks good at first, but 253 tiles are slow to scan and can't be sorted like columns.

## Principles

1. **Scan first, read second:** a row answers "how done is this?" at a glance, through the strip.
2. **Celeste's own words and colors:** sides, hearts, checkpoints. The page says *cleared*, *playing* and *not opened* for sides, and *playing* for a mod or level set in progress. (The CLI and the JSON keep "in progress": only the page's wording changes.)
3. **Form carries state:** fill, outline and dash say how far a side is; color only says which side.
4. **Motion only answers the player:** a row may expand smoothly when opened. No entrance animations.
5. **Each figure gets its own label**, not a dot-joined string (the Olympus ID line is the one exception, above).

## Rejected while planning

Checked against the `frontend-design` skill's list of generic defaults:

- The Journal's paper and handwriting look: cream paper is the most common AI-made look. Kept the Journal's columns and heart colors instead.
- A big stat banner as the opener: the totals are labeled figures in the top bar, and the table comes first.
- A pixel-art font for the wordmark: a second flourish next to the strips.
- Green for "complete": it clashed with the heart colors, and form now carries status.

## Build order

1. Font and tokens, side strips (with `by_side` from `rules.py`), side chips in heart colors, "playing".
2. One table with a header row, sorting by column header, Deaths column, labeled totals in the top bar, the Olympus-style second line.

Check each step with `playwright-cli` on the real saves (scratch config), light and dark.
