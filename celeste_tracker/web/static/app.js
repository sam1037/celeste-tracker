"use strict";
// The tracker page. It only draws what /api/library sends: statuses and totals are decided by the server
// (rules.py). State lives in the URL hash (#slot=…&show=…&open=…), so a view can be bookmarked or reloaded.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cls = (s) => String(s || "").toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "");
const pad = (n) => String(n).padStart(2, "0");
const TICKS = 10_000_000;
const fmtNum = (n) => (n || 0).toLocaleString("en-US");
const SEP = "\n"; // between IDs in the hash: mod IDs can contain commas and spaces

function fmtTime(ticks) {
  const s = Math.floor((ticks || 0) / TICKS), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}

const PER_PAGE = 50;
const DIFFICULTIES = ["Beginner", "Intermediate", "Advanced", "Expert", "Grandmaster"];  // as in store.py
const MAX_TAG = 30;
const cleanTag = (t) => t.toLowerCase().split(/\s+/).filter(Boolean).join(" ").slice(0, MAX_TAG);  // as store.clean_tag
const state = { data: null, key: "all", f: {}, tagAll: false, sort: "time", dir: "", page: 1, per: PER_PAGE, q: "", open: new Set(), openSet: new Set(),
                openCh: new Set() };
const setId = (m, ls) => `${m.id}/${ls.name}`; // a level set can be split across mods (Glyph + Glyph D side)
let index = { modOfSid: {}, search: {} };
let sessionsOpen = null; // the player's choice once they open or close the panel

// ------------------------------------------------------------------ URL hash

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.key = p.get("slot") || "all";
  // The filters, one list per line of the Filter panel; show= is the Show menu's, from before the panel.
  for (const g of FILTER_GROUPS) {
    const ok = g.dynamic ? null : new Set(g.opts().map((o) => o.id));  // the tags aren't known before loading
    state.f[g.id] = (p.get(g.id) || "").split(SEP).filter((x) => x && (!ok || ok.has(x))).slice(0, g.multi ? undefined : 1);
  }
  state.tagAll = p.get("tagall") === "1";
  const show = OLD_SHOW[p.get("show")] ?? p.get("show");
  if (show && !state.f.st.length && FILTER_GROUPS[0].opts().some((o) => o.id === show)) state.f.st = [show];
  state.sort = SORT_COLUMN[p.get("sort")] ? p.get("sort") : "time";
  state.dir = ["asc", "desc"].includes(p.get("dir")) ? p.get("dir") : "";
  state.page = Math.max(1, parseInt(p.get("page"), 10) || 1);
  state.per = p.has("per") ? Math.max(0, parseInt(p.get("per"), 10) || 0) : PER_PAGE;  // 0 = all on one page
  state.q = p.get("q") || "";
  state.open = new Set((p.get("open") || "").split(SEP).filter(Boolean));
  state.openSet = new Set((p.get("sets") || "").split(SEP).filter(Boolean));
  state.openCh = new Set((p.get("ch") || "").split(SEP).filter(Boolean));
}

function writeHash() {
  const p = new URLSearchParams();
  if (state.key !== "all") p.set("slot", state.key);
  for (const g of FILTER_GROUPS) if (state.f[g.id].length) p.set(g.id, state.f[g.id].join(SEP));
  if (state.tagAll && state.f.tag.length) p.set("tagall", "1");
  if (state.sort !== "time") p.set("sort", state.sort);
  if (state.dir && state.dir !== FIRST_DIR[SORT_COLUMN[state.sort]]) p.set("dir", state.dir);
  if (state.page > 1) p.set("page", state.page);
  if (state.per !== PER_PAGE) p.set("per", state.per);
  if (state.q) p.set("q", state.q);
  if (state.open.size) p.set("open", [...state.open].join(SEP));
  if (state.openSet.size) p.set("sets", [...state.openSet].join(SEP));
  if (state.openCh.size) p.set("ch", [...state.openCh].join(SEP));
  history.replaceState(null, "", p.toString() ? "#" + p : location.pathname);
}

// ------------------------------------------------------------------ data helpers

const known = (m) => m.found || m.vanilla;
const q = (m) => (known(m) ? "" : "?"); // totals of a mod that isn't in the Mods folder only cover what was opened

function viewOf(node, notOpened = "not started") {
  // A node has no view for a slot it wasn't played in: show it as not started, with the catalog's totals.
  const v = node.progress[state.key];
  if (v) return v;
  const all = node.progress.all || {};
  return { status: notOpened, sides_done: 0, hearts: 0, sides_total: all.sides_total || 0, maps_done: 0,
           maps_total: all.maps_total || 0,
           by_side: Object.fromEntries(Object.entries(all.by_side || {}).map(([k, [, t]]) => [k, [0, t]])), deaths: 0, ticks: 0, berries: 0, slots: [], loaded: true,
           latest_checkpoint: null, open_checkpoints: 0 };
}

const chapters = (m) => m.sets.flatMap((s) => s.chapters);
const countedSides = (ch) => Object.values(ch.sides).filter((s) => s.exists || s.progress[state.key]);

function buildIndex(data) {
  index = { modOfSid: {}, search: {} };
  for (const m of data.mods) {
    const words = [m.name, m.id, m.gamebanana_title, m.author, m.user.note, ...(m.user.tags || [])];
    for (const ls of m.sets) {
      words.push(ls.name, ls.title);
      for (const ch of ls.chapters) {
        index.modOfSid[ch.sid] = m;
        words.push(ch.sid, ch.title);
      }
    }
    index.search[m.id] = words.filter(Boolean).join("\n").toLowerCase();
  }
}

// The page uses three statuses at every level, mod, level set, chapter and side (doc/UI.md, "Statuses"): the
// server's "in progress" and "started" are both in progress; "complete", a side's or chapter's "completed" and
// "all opened done" (a mod not in the Mods folder, every opened side cleared, its totals marked "?") are all
// completed; "not opened" is not started. The CLI and the JSON keep the server's words.
const PAGE_STATUS = { started: "in progress", complete: "completed", "all opened done": "completed", "not opened": "not started" };
const pageStatus = (s) => PAGE_STATUS[s] || s;
const STATUS_HELP = {
  "in progress": "Opened, not finished: some sides still to clear",
  completed: "Every side cleared",
  "not started": "Never opened",
};
// The Filter panel (doc/UI.md, "Filters"): one line per group. Choices in one line widen the list (a mod needs one of
// them), lines narrow it (a mod needs every line). A group that isn't multi takes one choice at a time. The status
// IDs (playing, complete) are the old Show menu's, so bookmarks still work.
const FILTER_GROUPS = [
  { id: "st", label: "Status", multi: true, opts: () => [
    { id: "playing", label: "In progress", chip: "in progress", test: (m, v) => pageStatus(v.status) === "in progress" },
    { id: "complete", label: "Completed", chip: "completed", test: (m, v) => pageStatus(v.status) === "completed" },
    { id: "notstarted", label: "Not started", chip: "not started", test: (m, v) => v.status === "not started" },
  ] },
  { id: "rate", label: "Rating", opts: () => [
    { id: "5", label: "★ 5", test: (m) => m.user.rating === 5 },
    { id: "4", label: "★ 4 or more", test: (m) => m.user.rating >= 4 },
    { id: "3", label: "★ 3 or more", test: (m) => m.user.rating >= 3 },
    { id: "none", label: "Not rated", test: (m) => !m.user.rating },
  ] },
  { id: "diff", label: "Difficulty", multi: true, opts: () => [
    ...DIFFICULTIES.map((d) => ({ id: d, label: d, test: (m) => m.user.difficulty === d })),
    { id: "none", label: "Not set", test: (m) => !m.user.difficulty },
  ] },
  // The player's tags, from the data; "tagall" makes a mod need every tag picked instead of one of them.
  { id: "tag", label: "Tags", multi: true, dynamic: true, opts: () => allTags().map((t) => ({ id: t, label: t,
    test: (m) => (m.user.tags || []).includes(t) })) },
  { id: "note", label: "Note", opts: () => [
    { id: "yes", label: "Has a note", test: (m) => !!m.user.note },
    { id: "no", label: "No note", test: (m) => !m.user.note },
  ] },
];
const allTags = () => [...new Set((state.data?.mods || []).flatMap((m) => m.user.tags || []))].sort();
const OLD_SHOW = { all: "", played: "", dropped: "", unfinished: "playing" };  // Show menu values from before
const filtersOn = () => FILTER_GROUPS.filter((g) => state.f[g.id].length);
const passes = (m, v) => filtersOn().every((g) => {
  const picked = g.opts().filter((o) => state.f[g.id].includes(o.id));
  return g.id === "tag" && state.tagAll ? picked.length === state.f.tag.length && picked.every((o) => o.test(m, v))
    : picked.some((o) => o.test(m, v));
});
// The sort IDs kept in the URL (sort=…&dir=…), the column each sorts, and the direction a column starts in when
// clicked (names A to Z, numbers high to low). "status" is an old bookmark's, sorted as sides cleared now.
const SORT_COLUMN = { name: "mod", author: "author", progress: "sides", status: "sides", deaths: "deaths", time: "time",
                      rating: "rating", difficulty: "difficulty", slot: "slot" };
const FIRST_DIR = { mod: "asc", author: "asc", sides: "desc", deaths: "desc", time: "desc", rating: "desc",
                    difficulty: "asc", slot: "asc" };
const sortDir = () => state.dir || FIRST_DIR[SORT_COLUMN[state.sort]];

function visibleMods() {
  // The mods the filters and the search let through, in no order: the table sorts them.
  const needle = state.q.trim().toLowerCase();
  return state.data.mods.map((m) => ({ m, v: viewOf(m) }))
    .filter(({ m, v }) => passes(m, v) && (!needle || index.search[m.id].includes(needle)));
}

// ------------------------------------------------------------------ rendering

function bar(v) {
  // Sides cleared, in one color (doc/UI.md); hovering shows the count per side letter.
  const title = Object.entries(v.by_side || {}).map(([k, [d, t]]) => `${k} sides: ${d} of ${t} cleared`).join("\n");
  return `<div class="bar" title="${esc(title)}"><i style="width:${(100 * v.sides_done) / (v.sides_total || 1)}%"></i></div>`;
}

function status(s, unsure = false) {
  const st = pageStatus(s);
  const help = STATUS_HELP[st] + (unsure && st === "completed"
    ? ". This mod isn't in your Mods folder, so its real total is unknown: every side you opened is cleared" : "");
  return `<span class="status s-${cls(st)}" title="${esc(help)}">${esc(st)}</span>`;
}

function slotCell(v) {
  // All slots: the row shows one slot, the mod's furthest (rules.py); the other slots it was played in are in the
  // tooltip and in the opened mod's facts.
  if (!v.slot) return `<span class="num right hide-sm"></span>`;
  const others = v.slots.filter((k) => k !== v.slot);
  const title = `Shown: slot ${v.slot}, your furthest` + (others.length ? `. Also played in slot${others.length > 1 ? "s" : ""} ${others.join(", ")}` : "");
  return `<span class="num right hide-sm" title="${esc(title)}">${esc(v.slot)}</span>`;
}

function ownTags(m) {
  // "dropped", set with the CLI, on the mod's second line.
  return m.user.dropped ? `<span class="tag own">dropped</span>` : "";
}

function tagCell(m) {
  // The player's tags as small chips; the ones that don't fit are counted, and all are in the tooltip.
  const tags = m.user.tags || [];
  return `<span class="tagcell hide-sm"${tags.length ? ` title="${esc(tags.join(", "))}"` : ""}>` +
    tags.slice(0, 3).map((t) => `<span class="ptag">${esc(t)}</span>`).join("") +
    (tags.length > 3 ? `<span class="more">+${tags.length - 3}</span>` : "") + `</span>`;
}

function stars(m, where) {
  // The player's rating, 1 to 5, as a radio group (the WAI-ARIA rating pattern): one Tab stop, arrow keys move.
  // Clicking the star given clears it. where: "row" (the Rating column) or "panel" (the Yours panel).
  const r = m.user.rating || 0;
  return `<span class="rate${r ? " rated" : ""}${where === "row" ? " hide-sm" : ""}" role="radiogroup" ` +
    `aria-label="Your rating for ${esc(m.name)}" data-key="${esc(m.id)}" data-where="${where}">` +
    [1, 2, 3, 4, 5].map((n) => `<button type="button" role="radio" data-rate="${n}" aria-checked="${n === r}"` +
      ` tabindex="${n === (r || 1) ? 0 : -1}" class="${n <= r ? "on" : ""}" aria-label="${n} of 5"` +
      ` title="${n === r ? "Clear your rating" : `${n} of 5`}">${n <= r ? "★" : "☆"}</button>`).join("") + `</span>`;
}

// ------------------------------------------------------------------ columns

// The table's columns (doc/UI.md, "Columns"). Sides takes the width that's left; every other column has a width the
// player can drag (Tabulator's resizing, kept in the store). Every column but Mod can be hidden from the Columns
// menu; Best, Berries, Difficulty and Tags start hidden. Slot only shows with "All slots".
const COLUMNS = [
  { id: "mod", label: "Mod", width: 320, min: 160 },
  { id: "author", label: "Author", width: 170, min: 60 },
  { id: "sides", label: "Sides", min: 150, help: "Sides cleared" },
  { id: "deaths", label: "Deaths", width: 84, min: 72, right: true },
  { id: "time", label: "Time", width: 84, min: 64, right: true, help: "Time played" },
  { id: "best", label: "Best", width: 72, min: 56, right: true, help: "Best time, for a single side", unsorted: true },
  { id: "berries", label: "Berries", width: 84, min: 72, right: true, unsorted: true },
  { id: "rating", label: "Rating", width: 100, min: 100, mine: true, help: "How much you enjoyed it, 1 to 5" },
  { id: "difficulty", label: "Difficulty", width: 108, min: 80, mine: true, help: "How hard it is for you" },
  { id: "tags", label: "Tags", width: 150, min: 70, mine: true, help: "Your tags", unsorted: true },
  { id: "note", label: "Note", width: 200, min: 80, mine: true, help: "Your note: click one to write or change it", unsorted: true },
  { id: "slot", label: "Slot", width: 66, min: 60, right: true, help: "The slot shown: your furthest" },
];
const DEFAULT_HIDDEN = ["best", "berries", "difficulty", "tags"];
// When the columns shown don't fit, these give way in this order, down to their minimum, so the last column stays in
// view (only on screen: the saved widths stay). Tabulator's own widthShrink doesn't run while Sides, the flexible
// column, is at its minimum.
const SHRINK = ["mod", "author", "note", "tags", "difficulty"];

function fitWidths() {
  const shown = COLUMNS.filter(shows), sides = COLUMNS.find((c) => c.id === "sides");
  const w = Object.fromEntries(shown.filter((c) => c !== sides).map((c) => [c.id, prefs.widths[c.id] || c.width]));
  let over = Object.values(w).reduce((a, x) => a + x, 0) + (shows(sides) ? sides.min : 0) - ($("list").clientWidth - 2);
  for (const id of SHRINK) {
    const c = COLUMNS.find((x) => x.id === id);
    if (over <= 0 || !(id in w)) continue;
    const take = Math.min(over, Math.max(0, w[id] - c.min));
    w[id] -= take;
    over -= take;
  }
  return w;
}
// The columns there were before the page saved which ones it knew: a column added since starts as DEFAULT_HIDDEN says,
// even for a player whose saved settings don't mention it.
const OLD_COLUMNS = ["mod", "author", "sides", "deaths", "time", "best", "berries", "slot"];
let prefs = { hidden: DEFAULT_HIDDEN, widths: {}, auto: [] };  // auto: the player's columns that turned on by themselves

const canShow = (c) => c.id !== "slot" || state.key === "all";
const shows = (c) => c.id === "mod" || (canShow(c) && !prefs.hidden.includes(c.id));

async function loadPrefs() {
  try {
    const r = await fetch("/api/prefs");
    const p = r.ok ? await r.json() : {};
    const hidden = Array.isArray(p.hidden) ? p.hidden : DEFAULT_HIDDEN, known = Array.isArray(p.known) ? p.known : OLD_COLUMNS;
    prefs = { hidden: [...hidden, ...DEFAULT_HIDDEN.filter((id) => !known.includes(id) && !hidden.includes(id))],
              widths: p.widths && typeof p.widths === "object" ? p.widths : {}, auto: Array.isArray(p.auto) ? p.auto : [] };
  } catch { /* the defaults */ }
}

function savePrefs() {
  fetch("/api/prefs", { method: "POST", headers: { "Content-Type": "application/json", "X-Celeste-Tracker": "1" },
                        body: JSON.stringify({ ...prefs, known: COLUMNS.map((c) => c.id) }) }).catch(() => {});
}

function renderColumnsMenu() {
  // Two groups: what comes from the saves, and the player's own fields.
  const box = (c) => `<label${canShow(c) ? "" : ' class="muted" title="Only with All slots"'}><input type="checkbox" data-col="${c.id}"` +
    `${prefs.hidden.includes(c.id) ? "" : " checked"}${canShow(c) ? "" : " disabled"}> ${c.label}</label>`;
  $("cols").innerHTML = `<h4>From your saves</h4>` + COLUMNS.filter((c) => c.id !== "mod" && !c.mine).map(box).join("") +
    `<hr><h4>Yours</h4>` + COLUMNS.filter((c) => c.mine).map(box).join("") +
    `<button type="button" data-reset-cols>Reset columns</button>`;
}

let shownKey = "";
function syncColumns(force = false) {
  // Shows and hides the table's columns as the settings and the slot say, and fits their widths: the columns are
  // set again only when something about them changed.
  if (!table) return;
  const key = COLUMNS.filter(shows).map((c) => c.id).join() + "|" + $("list").clientWidth;
  if (key === shownKey && !force) return;
  shownKey = key;
  restoring = true;
  table.setColumns(columnDefs());
  const col = SORT_COLUMN[state.sort] || "time";
  table.setSort(col, sortDir());  // new columns lose the sort
  restoring = false;
}

// ------------------------------------------------------------------ cells

const notPlayed = (v) => v.status === "not started" || v.status === "not opened";
const dash = (v, text) => (notPlayed(v) ? "-" : text);

function progress(v, mark = "", unsure = false) {
  // The bar, "x/y sides" under it, and the status at the right under it: there's no Status column.
  return `<span class="progress">${bar(v)}<small><span class="num">${v.sides_done}/${v.sides_total}${mark} sides</span>` +
    `${status(v.status, unsure)}</small></span>`;
}

function sideView(s) {
  // A side not opened in this slot still counts as one side to clear.
  return s.progress[state.key] || { status: "not opened", sides_done: 0, sides_total: 1, deaths: 0, ticks: 0, berries: 0 };
}

function best(ch) {
  // The best time of a chapter's only side; chapters with several sides show theirs on the side rows.
  const sides = countedSides(ch);
  if (sides.length !== 1) return "";
  const v = sideView(sides[0]);
  return v.best_ticks ? fmtTime(v.best_ticks) : "-";
}

function setLabel(ls) {
  return ls.title || ls.name.split("/").pop(); // under its mod, the last part of the ID is enough ("0-Gyms")
}

function nameCell(d) {
  // The arrow (on rows that open), then the name; a mod has the dim Olympus-style line under it (doc/UI.md, "What
  // players already know"): ID ∙ details.
  const caret = `<span class="caret" aria-hidden="true">${d.opens ? "▸" : ""}</span>`;
  if (d.kind !== "mod") return `<span class="tname${d.kind === "set" ? " strong" : ""}">${caret}<span class="t">${esc(d.name)}</span></span>`;
  const m = d.m, sub = esc([m.id !== m.name ? m.id : "", m.sets.length > 1 ? `${m.sets.length} level sets` : ""]
    .filter(Boolean).join(" ∙ ")) + ownTags(m);
  return `<span class="mname">${caret}<span class="name">${esc(m.name)}${sub ? `<span class="sub">${sub}</span>` : ""}</span></span>`;
}

function slotText(v) {
  // All slots: the row shows one slot, the mod's furthest (rules.py); the other slots it was played in are in the
  // tooltip and in the opened mod's facts.
  if (!v.slot) return "";
  const others = v.slots.filter((k) => k !== v.slot);
  const title = `Shown: slot ${v.slot}, your furthest` + (others.length ? `. Also played in slot${others.length > 1 ? "s" : ""} ${others.join(", ")}` : "");
  return `<span class="num" title="${esc(title)}">${esc(v.slot)}</span>`;
}

// What each column draws, for a mod row (d.m set) and for the rows under it (level sets, chapters, sides).
const CELL = {
  mod: nameCell,
  author: (d) => (d.m ? `<span class="author" title="${esc(d.m.author ? `GameBanana author: ${d.m.author}` : "Not on GameBanana's mod list")}">${esc(d.m.author)}</span>` : ""),
  sides: (d) => progress(d.v, d.mark, d.kind === "mod" && d.mark === "?"),
  deaths: (d) => `<span class="num">${dash(d.v, fmtNum(d.v.deaths))}</span>`,
  time: (d) => `<span class="num">${dash(d.v, fmtTime(d.v.ticks))}</span>`,
  best: (d) => `<span class="num">${d.best}</span>`,
  berries: (d) => `<span class="num">${dash(d.v, fmtNum(d.v.berries))}</span>`,
  rating: (d) => (d.m ? stars(d.m, "row") : ""),
  difficulty: (d) => (d.m ? `<span class="diff">${esc(d.m.user.difficulty)}</span>` : ""),
  tags: (d) => (d.m ? tagCell(d.m) : ""),
  // Clicking it opens the mod with the cursor in its note, so an empty one is how to write one.
  note: (d) => (d.m ? `<span class="notecell" data-note-cell title="${esc(d.m.user.note || "Click to write a note")}">${esc(d.m.user.note)}</span>` : ""),
  slot: (d) => (d.m ? slotText(d.v) : ""),
};

// Sorting: each compares two mods in ascending order. Tabulator swaps them for a descending sort, so a sorter that
// keeps empty values last whichever way flips its own answer for those; ties go A to Z either way.
const diffRank = (m) => DIFFICULTIES.indexOf(m.user.difficulty) + 1;  // 0: not set (or an old free-text value)
const SORT_VALUE = {
  mod: null, author: (d) => d.m.author || null, sides: (d) => d.v.sides_done / (d.v.sides_total || 1),
  deaths: (d) => d.v.deaths, time: (d) => d.v.ticks, rating: (d) => d.m.user.rating || null,
  difficulty: (d) => diffRank(d.m) || null, slot: (d) => (d.v.slot ? Number(d.v.slot) : null),
};

function sorter(id) {
  return (a, b, ra, rb, col, dir) => {
    const da = ra.getData(), db = rb.getData(), byName = da.m.name.localeCompare(db.m.name) * (dir === "asc" ? 1 : -1);
    if (id === "mod") return da.m.name.localeCompare(db.m.name);
    const x = SORT_VALUE[id](da), y = SORT_VALUE[id](db);
    if ((x === null) !== (y === null)) return (x === null ? 1 : -1) * (dir === "asc" ? 1 : -1);
    if (x === null || x === y) return byName;
    return typeof x === "string" ? x.localeCompare(y) : x - y;
  };
}

// ------------------------------------------------------------------ the rows

// The tree (doc/UI.md, "Layout"): a mod opens to its level sets (a collab) or chapters, a level set to its chapters,
// and a chapter with more than one side to its sides. A one-chapter mod opens straight to its sides. Every mod
// opens, if only to its facts and the Yours panel.
const RANK = { "in progress": 0, completed: 1, "not opened": 2 };

function sideRows(ch, m) {
  return countedSides(ch).map((s) => {
    const v = sideView(s);
    return { id: `d:${ch.sid}:${s.side}`, kind: "side", name: `${s.side} side`, v, mark: "", best: v.best_ticks ? fmtTime(v.best_ticks) : "-" };
  });
}

function chapterRows(m, list) {
  return [...list]
    .sort((a, b) => (RANK[viewOf(a, "not opened").status] ?? 3) - (RANK[viewOf(b, "not opened").status] ?? 3))
    .map((ch) => {
      const many = countedSides(ch).length > 1;
      return { id: `c:${ch.sid}`, kind: "ch", key: ch.sid, opens: many, name: ch.title || ch.sid.split("/").pop(),
               v: viewOf(ch, "not opened"), mark: q(m), best: best(ch), ...(many ? { _children: sideRows(ch, m) } : {}) };
    });
}

function modRow({ m, v }) {
  const chs = chapters(m);
  let kids = [];
  if (chs.length === 1) kids = countedSides(chs[0]).length > 1 ? sideRows(chs[0], m) : [];
  else if (m.sets.length === 1) kids = chapterRows(m, m.sets[0].chapters);
  else kids = m.sets.map((ls) => ({ id: `s:${setId(m, ls)}`, kind: "set", key: setId(m, ls), opens: true, name: setLabel(ls),
                                    v: viewOf(ls), mark: q(m), best: "", _children: chapterRows(m, ls.chapters) }));
  return { id: `m:${m.id}`, kind: "mod", key: m.id, opens: true, m, v, mark: q(m), best: chs.length === 1 ? best(chs[0]) : "",
           ...(kids.length ? { _children: kids } : {}) };
}

const OPEN = { mod: () => state.open, set: () => state.openSet, ch: () => state.openCh };
const isOpen = (d) => !!OPEN[d.kind]?.().has(d.key);

// ------------------------------------------------------------------ the opened mod

function modBody(m, v) {
  const facts = [`<span>Mod ID <b>${esc(m.id)}</b></span>`];
  if (m.gamebanana_title && m.gamebanana_title !== m.name) facts.push(`<span>GameBanana <b>${esc(m.gamebanana_title)}</b></span>`);
  facts.push(`<span>Hearts collected <b>${v.hearts}</b></span>`);
  if (state.key === "all" && v.slot) facts.push(`<span>${shownSlot(m, v)}</span>`);
  if (!known(m)) facts.push(`<span>Not in the Mods folder: only what you opened is listed</span>`);
  // Not on the row: on most rows, and it doesn't help pick what to play (user, 2026-10-08).
  if (!v.loaded) facts.push(`<span>Everest didn't load this mod the last time the game saved</span>`);
  return `<div class="facts">${facts.join("")}</div>${yours(m)}`;
}

function shownSlot(m, v) {
  // "Shown: slot 1, your furthest; also played in slot 2 (2/3 sides), slot 31 (0/3 sides)". Every number on an
  // opened mod comes from the slot shown; more than 6 other slots are just counted.
  const others = v.slots.filter((k) => k !== v.slot);
  if (!others.length) return `From slot <b>${esc(v.slot)}</b>, the only one it was played in`;
  const list = others.length > 6 ? `${others.length} other slots`
    : others.map((k) => `slot ${esc(k)} (${m.progress[k].sides_done}/${m.progress[k].sides_total} sides)`).join(", ");
  return `Shown: <b>slot ${esc(v.slot)}</b>, your furthest; also played in ${list}`;
}

// The Yours panel, in an opened mod: every field the player sets on it, in one place (doc/UI.md, "Your fields").
// Dropped and the rename are still only set with the CLI.
function yours(m) {
  const id = `note-${cls(m.id)}`, d = m.user.difficulty || "";
  const levels = DIFFICULTIES.includes(d) || !d ? DIFFICULTIES : [...DIFFICULTIES, d];  // an old free-text value stays
  return `<section class="yours" data-key="${esc(m.id)}" aria-label="Yours">
    <h3>Yours <span>Only you see these. Your save files are never changed.</span></h3>
    <span class="lab">Rating</span>${stars(m, "panel")}
    <label for="diff-${id}">Difficulty</label>
    <select id="diff-${id}" data-difficulty><option value="">Not set</option>` +
      levels.map((x) => `<option${x === d ? " selected" : ""}>${esc(x)}</option>`).join("") + `</select>
    <span class="lab">Tags</span>
    <span class="tags">${(m.user.tags || []).map((t) => `<span class="ptag">${esc(t)}<button type="button" data-untag="${esc(t)}"` +
      ` aria-label="Remove the tag ${esc(t)}" title="Remove">✕</button></span>`).join("")}` +
      `<input type="text" data-addtag list="tag-list" maxlength="${MAX_TAG}" placeholder="Add a tag" aria-label="Add a tag"></span>
    <label class="note-lab" for="${id}">Note</label>
    <textarea id="${id}" data-note rows="1" maxlength="${NOTE_MAX}" placeholder="Add a note: where you stopped, what to try next">${esc(m.user.note)}</textarea>
    <span></span><span class="saved" aria-live="polite"></span>
  </section>`;
}

function formatRow(row) {
  // Tabulator calls this for every row it draws: the row's classes, the keyboard, and an opened mod's facts and
  // Yours panel, inside the mod's row so they sit between it and the rows under it.
  const d = row.getData(), el = row.getElement();
  el.dataset.kind = d.kind;
  el.classList.toggle("open", isOpen(d));
  el.classList.toggle("dropped", !!d.m?.user.dropped);
  el._row = row;
  if (d.opens) { el.tabIndex = 0; el.setAttribute("aria-expanded", isOpen(d)); }
  el.querySelector(":scope > .mod-body")?.remove();
  if (d.kind === "mod" && isOpen(d)) {
    el.insertAdjacentHTML("beforeend", `<div class="mod-body">${modBody(d.m, d.v)}</div>`);
    for (const area of el.querySelectorAll("[data-note]")) requestAnimationFrame(() => fitNote(area));
  }
}

// ------------------------------------------------------------------ the table

let table = null, passing = new Set(), restoring = false;

function columnDefs() {
  const fit = fitWidths();
  return COLUMNS.map((c) => ({
    field: c.id, title: c.label, headerTooltip: c.help || false, visible: shows(c),
    minWidth: c.min, ...(c.id === "sides" ? { widthGrow: 1 } : { width: fit[c.id] || prefs.widths[c.id] || c.width }),
    cssClass: c.right ? "cell-right" : "", resizable: c.id !== "sides",
    headerSort: !c.unsorted, headerSortStartingDir: FIRST_DIR[c.id] || "asc", sorter: c.unsorted ? undefined : sorter(c.id),
    formatter: (cell) => CELL[c.id](cell.getRow().getData()),
  }));
}

function makeTable() {
  const col = SORT_COLUMN[state.sort] || "time";
  table = new Tabulator("#list", {
    index: "id", data: [], columns: columnDefs(), layout: "fitColumns", renderVertical: "basic", keybindings: false,
    resizableColumnFit: true,  // dragging a line only moves that line: the column on its other side gives the width
    dataTree: true, dataTreeStartExpanded: (row) => isOpen(row.getData()), dataTreeElementColumn: "mod",
    dataTreeSort: false, dataTreeFilter: false,  // the rows under a mod keep their order, and the filters are per mod
    dataTreeChildIndent: 20, dataTreeBranchElement: false,
    dataTreeExpandElement: "<span></span>", dataTreeCollapseElement: "<span></span>",  // nameCell draws the arrow
    initialSort: [{ column: col, dir: state.dir || FIRST_DIR[col] }], headerSortTristate: false,
    // ↕ marks a column you can sort by, ▲ / ▼ the one sorted now, right after its name (doc/UI.md, "Layout").
    headerSortElement: (column, dir) => (dir === "asc" ? "▲" : dir === "desc" ? "▼" : "↕"),
    pagination: true, paginationMode: "local", paginationSize: state.per || 100000, paginationSizeSelector: [25, 50, 100, true],
    paginationButtonCount: 5,
    // Counted in mods: Tabulator's own count includes the rows under an opened mod.
    paginationCounter: (size, row, page) => (passing.size ? `${fmtNum((page - 1) * size + 1)}–${fmtNum(Math.min(passing.size, page * size))} of ${fmtNum(passing.size)} mods` : ""),
    langs: { default: { pagination: { page_size: "Rows per page", first: "First", first_title: "First page", last: "Last",
      last_title: "Last page", prev: "‹ Previous", prev_title: "Previous page", next: "Next ›", next_title: "Next page", all: "All" } } },
    placeholder: "No mods match. Clear the search or the filters.",
    rowFormatter: formatRow,
  });
  table.on("dataSorted", (sorters) => {
    if (restoring || !sorters.length) return;
    const id = sorters[0].field;
    state.sort = Object.keys(SORT_COLUMN).find((k) => SORT_COLUMN[k] === id);
    state.dir = sorters[0].dir === FIRST_DIR[id] ? "" : sorters[0].dir;
    writeHash();
  });
  table.on("pageLoaded", (page) => { if (!restoring) { state.page = page; writeHash(); } });
  table.on("pageSizeChanged", (size) => { state.per = size === true || size > 1000 ? 0 : size; writeHash(); });
  table.on("columnResized", (column) => {
    prefs.widths = { ...prefs.widths, [column.getField()]: Math.round(column.getWidth()) };
    savePrefs();
  });
  table.on("rowClick", (e, row) => {
    if (e.target.closest("button, input, select, textarea, a, [data-note-cell], .mod-body")) return;
    toggleRow(row);
  });
  return new Promise((done) => table.on("tableBuilt", done));
}

function toggleRow(row) {
  // A mod, level set or chapter row: open or close it. A mod opens to its facts and Yours panel, and to the rows under
  // it when it has any.
  const d = row.getData();
  if (!d.opens) return;
  const set = OPEN[d.kind](), open = !set.has(d.key);
  open ? set.add(d.key) : set.delete(d.key);
  if (d._children) open ? row.treeExpand() : row.treeCollapse();
  row.reformat();
  writeHash();
}

async function fillTable() {
  // New data or another slot: every row is built again. The sort, the filter and the page are put back.
  restoring = true;
  await table.setData(state.data.mods.map((m) => modRow({ m, v: viewOf(m) })));
  refilter();
  if (state.page > 1) await table.setPage(Math.min(state.page, table.getPageMax() || 1));
  restoring = false;
}

function refilter() {
  passing = new Set(visibleMods().map(({ m }) => m.id));
  table.setFilter((d) => d.kind !== "mod" || passing.has(d.key));
}

function refreshMod(key) {
  // Draws one mod's row again after an edit (its cells and, when open, its panel).
  table?.getRow(`m:${key}`)?.reformat();
}

// ------------------------------------------------------------------ the rest of the page

function renderSummary(rows) {
  const played = state.data.mods.map((m) => viewOf(m)).filter((v) => v.status !== "not started");
  const done = played.filter((v) => pageStatus(v.status) === "completed").length;
  const sides = played.reduce((a, v) => [a[0] + v.sides_done, a[1] + v.sides_total], [0, 0]);
  const fig = (label, n, of) => `<span>${label} <b>${fmtNum(n)}</b>${of === undefined ? "" : ` of ${fmtNum(of)}`}</span>`;
  $("summary").innerHTML = fig("Sides completed", sides[0], sides[1]) + fig("Mods completed", done, played.length) +
    (filtersOn().length || state.q.trim() ? fig("Showing", rows.length) : "");
}

function renderFilters(rows) {
  // The Filter button (how many lines are on), its panel (each choice with how many mods it has in the slot shown)
  // and the chips under the toolbar.
  const all = state.data.mods.map((m) => ({ m, v: viewOf(m) })), on = filtersOn();
  $("filter-menu").classList.toggle("active", on.length > 0);
  $("filter-count").textContent = on.length || "";
  $("filter-count").hidden = !on.length;
  const line = (g) => {
    const opts = g.opts();
    if (!opts.length) return `<span class="lab">${g.label}</span><span class="none">None yet: add tags in an opened mod.</span>`;
    const chips = `<span class="opts">` + opts.map((o) => `<button type="button" class="opt" data-f="${g.id}" data-v="${esc(o.id)}"` +
      ` aria-pressed="${state.f[g.id].includes(o.id)}">${esc(o.label)}<small>${all.filter(({ m, v }) => o.test(m, v)).length}</small></button>`).join("") + `</span>`;
    const any = g.id === "tag" ? `<span class="any">A mod needs <select data-tagall><option value="">any of them</option>` +
      `<option value="1"${state.tagAll ? " selected" : ""}>all of them</option></select></span>` : "";
    return `<span class="lab">${g.label}</span><span>${chips}${any}</span>`;
  };
  $("filters").innerHTML = FILTER_GROUPS.map(line).join("") +
    `<hr><div class="foot"><span>${on.length ? `${fmtNum(rows.length)} of ${fmtNum(all.length)} mods match` : `All ${fmtNum(all.length)} mods`}` +
    `${state.q.trim() ? " the search" : ""}</span><button type="button" data-clear-filters${on.length ? "" : " disabled"}>Clear filters</button></div>`;
  $("chips").hidden = !on.length;
  $("chips").innerHTML = on.map((g) => `<span class="chip-f">${g.label} <b>` +
    esc(g.opts().filter((o) => state.f[g.id].includes(o.id)).map((o) => o.chip || o.label)
      .join(g.id === "tag" && state.tagAll ? " and " : ", ")) +
    `</b><button type="button" data-unfilter="${g.id}" aria-label="Remove the ${g.label} filter" title="Remove">✕</button></span>`).join("") +
    `<button type="button" class="clear" data-clear-filters>Clear filters</button>` +
    `<span class="shown">${fmtNum(rows.length)} of ${fmtNum(all.length)} mods</span>`;
}

function renderSessions() {
  // Where you left off: one row per slot saved inside a chapter (Save & Quit). The save has no dates, so rows
  // are in slot order. The checkpoint is the last one the save lists for that side (the start checkpoint is
  // empty in every real save seen); the room ID is a detail.
  const el = $("sessions");
  const slots = state.data.slots.filter((s) => s.session && (state.key === "all" || s.key === state.key));
  if (!slots.length) { el.hidden = true; return; }
  el.hidden = false;
  const open = sessionsOpen ?? (state.key !== "all" || slots.length <= 3);
  const rows = slots.map((s) => {
    const x = s.session, m = index.modOfSid[x.sid];
    const chapter = x.title && m && x.title === m.name ? "" : (x.title || x.sid);
    const cp = x.checkpoints.length ? x.checkpoints[x.checkpoints.length - 1] : null;
    const v = m && m.progress[s.key];
    return `<tr${m ? ` data-goto="${esc(m.id)}" title="Open ${esc(m.name)}"` : ""}>
      <td class="num">${esc(s.key)}</td>
      <td>${m ? `<a data-goto="${esc(m.id)}">${esc(m.name)}</a>` : esc(x.sid)}</td>
      <td>${esc(chapter)}</td>
      <td><span class="chip c-in-progress">${esc(x.side)}</span></td>
      <td>${cp ? esc(cp.title || cp.room) : '<span class="muted">start</span>'}</td>
      <td class="muted room">${esc(x.room)}</td>
      <td class="right num">${fmtNum(x.deaths)}</td>
      <td class="right num">${v ? `${v.sides_done}/${v.sides_total}` : "-"}</td></tr>`;
  }).join("");
  el.innerHTML = `<details${open ? " open" : ""}><summary>Where you left off ` +
    `<span class="muted">Save &amp; Quit in ${slots.length} slot${slots.length > 1 ? "s" : ""}</span></summary>
    <table class="resume"><colgroup><col class="w-slot"><col><col><col class="w-side"><col><col><col class="w-deaths"><col class="w-n">
    </colgroup><thead><tr><th>Slot</th><th>Mod</th><th>Chapter</th><th>Side</th><th>Last checkpoint</th><th>Room</th>
    <th class="right">Deaths this session</th><th class="right">Sides</th></tr></thead><tbody>${rows}</tbody></table></details>`;
}

function render() {
  // Everything around the table, then the table's filter. The table's rows are rebuilt only by fillTable.
  if (!state.data) return;
  const rows = visibleMods();
  renderSummary(rows);
  renderFilters(rows);
  $("tag-list").innerHTML = allTags().map((t) => `<option value="${esc(t)}">`).join("");
  renderSessions();
  renderColumnsMenu();
  syncColumns();
  if (table) refilter();
  writeHash();
}

function measure() {
  // Where the sticky header stops (style.css): under the top bar.
  document.documentElement.style.setProperty("--top-h", `${document.querySelector(".top").offsetHeight}px`);
}
let resizeTimer;
window.addEventListener("resize", () => { measure(); clearTimeout(resizeTimer); resizeTimer = setTimeout(syncColumns, 150); });

// ------------------------------------------------------------------ loading and editing

async function load(refresh = false) {
  try {
    const r = await fetch("/api/library" + (refresh ? "?refresh=1" : ""));
    if (!r.ok) throw new Error(`the server answered ${r.status}`);
    state.data = await r.json();
    buildIndex(state.data);
    fillSlots();
    $("error").hidden = true;
    if (!table) await makeTable();
    render();
    await fillTable();
    measure();
  } catch (e) {
    $("error").hidden = false;
    $("error").textContent = `Couldn't load your progress: ${e.message}. Is the tracker still running?`;
  }
}

function fillSlots() {
  const slots = state.data.slots;
  if (state.key !== "all" && !slots.some((s) => s.key === state.key)) state.key = "all";
  const opts = [`<option value="all">${slots.length > 1 ? `All slots (${slots.length})` : "This slot"}</option>`]
    .concat(slots.length > 1 ? slots.map((s) => `<option value="${esc(s.key)}">Slot ${esc(s.key)}${s.name ? `: ${esc(s.name)}` : ""}</option>`) : []);
  $("slot").innerHTML = opts.join("");
  $("slot").value = state.key;
}

const NOTE_MAX = 2000; // as in server.py

async function save(key, field, value) {
  // Saves one of the player's fields and updates the page's own copy, without reloading: a reload would redraw the
  // note field being typed in. The live reload (poll) picks up anything else that changed once the player is done.
  const r = await fetch("/api/user", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Celeste-Tracker": "1" },
    body: JSON.stringify({ key, field, value }),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `the server answered ${r.status}`);
  const m = state.data.mods.find((x) => x.id === key);
  if (value === "" || value === 0 || value === false || value == null || (Array.isArray(value) && !value.length)) delete m.user[field];
  else m.user[field] = typeof value === "string" ? value.trim() : value;
  buildIndex(state.data);  // the search matches notes and tags
}

async function rate(group, n) {
  // A star clicked or chosen with the arrow keys; the same star again clears the rating. Focus stays on the stars.
  const key = group.dataset.key, where = group.dataset.where, m = state.data.mods.find((x) => x.id === key);
  const value = m.user.rating === n ? 0 : n;
  try { await save(key, "rating", value); } catch (e) { return alert(`Couldn't save your rating: ${e.message}`); }
  refreshMod(key);
  render();
  const again = document.querySelector(`.rate[data-key="${CSS.escape(key)}"][data-where="${where}"]`);
  again?.querySelector(`[data-rate="${value || n}"]`)?.focus();
}

// The first time the player sets a difficulty or adds a tag, that column turns on by itself, once, with a notice
// that says so (doc/UI.md, "Your fields"); hiding it again from the Columns menu sticks.
function firstUse(col) {
  if (prefs.auto.includes(col)) return;
  prefs.auto = [...prefs.auto, col];
  if (prefs.hidden.includes(col)) {
    prefs.hidden = prefs.hidden.filter((x) => x !== col);
    const c = COLUMNS.find((x) => x.id === col);
    $("notice").innerHTML = `<span>The <b>${c.label}</b> column is on now that you've ${col === "tags" ? "added a tag" : "set one"}.</span>` +
      `<button type="button" data-notice-hide="${col}">Hide it</button><button type="button" data-notice-ok>OK</button>`;
    $("notice").hidden = false;
  }
  savePrefs();
}

async function setDifficulty(select) {
  const key = select.closest(".yours").dataset.key;
  try { await save(key, "difficulty", select.value); } catch (e) { return alert(`Couldn't save the difficulty: ${e.message}`); }
  if (select.value) firstUse("difficulty");
  refreshMod(key);
  render();
  document.querySelector(`.yours[data-key="${CSS.escape(key)}"] [data-difficulty]`)?.focus();
}

async function setTags(key, tags) {
  // Saves a mod's tags, then puts the cursor back in its "Add a tag" field.
  const clean = [...new Set(tags.map(cleanTag).filter(Boolean))].sort();
  try { await save(key, "tags", clean); } catch (e) { return alert(`Couldn't save the tags: ${e.message}`); }
  if (clean.length) firstUse("tags");
  refreshMod(key);
  render();
  document.querySelector(`.yours[data-key="${CSS.escape(key)}"] [data-addtag]`)?.focus();
}

function addTag(input) {
  const key = input.closest(".yours").dataset.key, tag = cleanTag(input.value);
  if (!tag) return;
  const m = state.data.mods.find((x) => x.id === key);
  input.value = "";
  if (!(m.user.tags || []).includes(tag)) setTags(key, [...(m.user.tags || []), tag]);
}

// Notes save 600 ms after typing stops, and when the field is left.
const noteTimers = {};
async function saveNote(area) {
  const key = area.closest(".yours").dataset.key, status = area.closest(".yours").querySelector(".saved");
  clearTimeout(noteTimers[key]);
  const m = state.data.mods.find((x) => x.id === key);
  if (area.value.trim() === (m.user.note || "")) return;
  try {
    await save(key, "note", area.value);
    status.textContent = "Saved";
    status.classList.remove("error");
    setTimeout(() => { if (status.textContent === "Saved") status.textContent = ""; }, 1500);
    // Once the player has left the panel, redraw the row so the Note column shows it.
    if (!document.activeElement?.closest(".yours")) { refreshMod(key); render(); }
  } catch (e) {
    status.textContent = `Not saved: ${e.message}`;
    status.classList.add("error");
  }
}

function fitNote(area) {
  // The note field grows with its text, up to the max-height in style.css.
  area.style.height = "auto";
  area.style.height = `${area.scrollHeight + 2}px`;
}

async function poll() {
  // The server bumps its version when a save file changes (the game saved): reload then, unless the
  // player is typing in one of the edit fields.
  try {
    const r = await fetch("/api/status");
    const { version } = await r.json();
    $("live").classList.add("on");
    const typing = document.activeElement && document.activeElement.closest(".yours");
    if (state.data && version !== state.data.version && !typing) await load();
  } catch {
    $("live").classList.remove("on");
  }
}

function openMod(id, { focusNote = false } = {}) {
  // Opens a mod (the Note column, "Where you left off"): goes to the page that has it and brings it into view.
  const row = table.getRow(`m:${id}`);
  if (!row) return;
  if (!state.open.has(id)) toggleRow(row);
  table.setPageToRow(row).then(() => {
    const area = row.getElement().querySelector("[data-note]");
    if (focusNote && area) {
      area.focus({ preventScroll: true });
      area.closest(".yours").scrollIntoView({ block: "nearest" });
    } else row.getElement().scrollIntoView({ block: "start" });
  });
}

// ------------------------------------------------------------------ events

$("list").addEventListener("click", (e) => {
  const star = e.target.closest("[data-rate]");
  if (star) return rate(star.closest(".rate"), Number(star.dataset.rate));
  if (e.target.closest("[data-note-cell]")) return openMod(e.target.closest(".tabulator-row")._row.getData().key, { focusNote: true });
  const untag = e.target.closest("[data-untag]");
  if (untag) {
    const key = untag.closest(".yours").dataset.key, m = state.data.mods.find((x) => x.id === key);
    return setTags(key, (m.user.tags || []).filter((t) => t !== untag.dataset.untag));
  }
});
$("list").addEventListener("keydown", (e) => {
  if (e.target.matches("[data-addtag]") && (e.key === "Enter" || e.key === ",")) {
    e.preventDefault();
    return addTag(e.target);
  }
  const star = e.target.closest("[data-rate]");
  const step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[e.key];
  if (star && step) {
    e.preventDefault();
    const m = state.data.mods.find((x) => x.id === star.closest(".rate").dataset.key);
    const n = Math.min(5, Math.max(1, (m.user.rating || 0) + step));
    if (n !== m.user.rating) rate(star.closest(".rate"), n);
    return;
  }
  // Enter or Space on a focused row opens or closes it.
  if ((e.key === "Enter" || e.key === " ") && e.target.classList.contains("tabulator-row") && e.target._row) {
    e.preventDefault();
    const row = e.target._row;
    toggleRow(row);
    row.getElement().focus({ preventScroll: true });  // redrawing the row drops the focus
  }
});
$("list").addEventListener("change", (e) => {
  if (e.target.matches("[data-difficulty]")) return setDifficulty(e.target);
  if (e.target.matches("[data-addtag]")) return addTag(e.target);
});
$("list").addEventListener("input", (e) => {
  if (!e.target.matches("[data-note]")) return;
  fitNote(e.target);
  const key = e.target.closest(".yours").dataset.key;
  clearTimeout(noteTimers[key]);
  noteTimers[key] = setTimeout(() => saveNote(e.target), 600);
});
$("list").addEventListener("focusout", (e) => { if (e.target.matches("[data-note]")) saveNote(e.target); });
// Hovering a star previews the rating up to it.
$("list").addEventListener("mouseover", (e) => {
  for (const b of document.querySelectorAll(".rate .preview")) b.classList.remove("preview");
  const star = e.target.closest("[data-rate]");
  if (!star) return;
  for (const b of star.parentElement.children) if (Number(b.dataset.rate) <= Number(star.dataset.rate)) b.classList.add("preview");
});
$("cols").addEventListener("change", (e) => {
  const id = e.target.dataset.col;
  if (!id) return;
  prefs.hidden = e.target.checked ? prefs.hidden.filter((x) => x !== id) : [...prefs.hidden, id];
  savePrefs();
  render();
});
$("cols").addEventListener("click", (e) => {
  if (!e.target.closest("[data-reset-cols]")) return;
  prefs = { hidden: DEFAULT_HIDDEN, widths: {}, auto: prefs.auto };
  savePrefs();
  syncColumns(true);
  render();
});
// The Columns and Filter menus close on a click anywhere else, or Escape.
const MENUS = ["cols-menu", "filter-menu"];
document.addEventListener("click", (e) => {
  // composedPath, not contains: a click in the Filter panel redraws it, so the clicked button is gone by now
  for (const id of MENUS) if ($(id).open && !e.composedPath().includes($(id))) $(id).open = false;
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") for (const id of MENUS) $(id).open = false; });

// Help: the ? button or the ? key opens it; Escape (the dialog's own), the ✕ or a click outside closes it.
$("help-open").addEventListener("click", () => $("help").showModal());
$("help").addEventListener("click", (e) => {
  if (e.target.closest("[data-close-help]") || e.target === $("help")) $("help").close();  // the backdrop is the dialog itself
});
$("sessions").addEventListener("toggle", (e) => { sessionsOpen = e.target.open; }, true);
$("sessions").addEventListener("click", (e) => {
  const a = e.target.closest("[data-goto]");
  if (!a) return;
  state.q = "";
  $("q").value = "";
  render();
  openMod(a.dataset.goto);
});

let typingTimer;
$("q").addEventListener("input", (e) => {
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => { state.q = e.target.value; render(); }, 150);
});
$("slot").addEventListener("change", (e) => { state.key = e.target.value; render(); fillTable(); });
document.addEventListener("change", (e) => {
  if (!e.target.matches("[data-tagall]")) return;
  state.tagAll = e.target.value === "1";
  render();
});
$("notice").addEventListener("click", (e) => {
  const hide = e.target.closest("[data-notice-hide]");
  if (hide) { prefs.hidden = [...prefs.hidden, hide.dataset.noticeHide]; savePrefs(); render(); }
  if (hide || e.target.closest("[data-notice-ok]")) $("notice").hidden = true;
});
// The Filter panel: a choice toggles; in a group that takes one choice, picking one drops the other.
document.addEventListener("click", (e) => {
  const opt = e.target.closest("[data-f]"), un = e.target.closest("[data-unfilter]");
  if (opt) {
    const g = FILTER_GROUPS.find((x) => x.id === opt.dataset.f), v = opt.dataset.v, cur = state.f[g.id];
    state.f[g.id] = cur.includes(v) ? cur.filter((x) => x !== v) : g.multi ? [...cur, v] : [v];
  } else if (un) state.f[un.dataset.unfilter] = [];
  else if (e.target.closest("[data-clear-filters]")) for (const g of FILTER_GROUPS) state.f[g.id] = [];
  else return;
  render();
});
$("refresh").addEventListener("click", () => load(true));
// "/" jumps to the search, as on GitHub and YouTube, unless the player is typing somewhere already.
document.addEventListener("keydown", (e) => {
  if (e.key === "?" && !e.ctrlKey && !e.metaKey && !e.altKey && !e.target.closest("input, textarea, select") && !$("help").open) {
    e.preventDefault();
    return $("help").showModal();
  }
  if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, textarea, select")) return;
  e.preventDefault();
  $("q").focus();
  $("q").select();
});

readHash();
$("q").value = state.q;
loadPrefs().then(() => load());
setInterval(poll, 5000);
