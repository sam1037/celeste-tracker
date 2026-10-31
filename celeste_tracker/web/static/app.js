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
  state.sort = SORTS[p.get("sort")] ? p.get("sort") : "time";
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
  if (state.dir && state.dir !== FIRST_DIR[state.sort]) p.set("dir", state.dir);
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
  index = { modOfSid: {}, chapterOfSid: {}, search: {} };
  for (const m of data.mods) {
    const words = [m.name, m.id, m.gamebanana_title, m.author, m.user.note, ...(m.user.tags || [])];
    for (const ls of m.sets) {
      words.push(ls.name, ls.title);
      for (const ch of ls.chapters) {
        index.modOfSid[ch.sid] = m;
        index.chapterOfSid[ch.sid] = ch;
        words.push(ch.sid, ch.title);
      }
    }
    index.search[m.id] = words.filter(Boolean).join("\n").toLowerCase();
  }
}

// The page uses three statuses at every level, mod, level set, chapter and side (docs/UI.md, "Statuses"): the
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
// The Filter panel (docs/UI.md, "Filters"): one line per group. Choices in one line widen the list (a mod needs one of
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
const STATUS_RANK = { "in progress": 0, completed: 1, "not started": 2 };
// Sort keys, each comparing in ascending order; FIRST_DIR is the direction a column starts in when clicked
// (names A to Z, numbers high to low). Clicking the sorted column again flips it. dir is the direction sorted in.
const SORTS = {
  time: (a, b) => a.v.ticks - b.v.ticks,
  progress: (a, b) => a.v.sides_done / (a.v.sides_total || 1) - b.v.sides_done / (b.v.sides_total || 1),
  name: (a, b) => a.m.name.localeCompare(b.m.name),
  // A to Z; mods without an author (not on GameBanana) last, whichever way the column is sorted
  author: (a, b, dir) => (!a.m.author - !b.m.author) * (dir === "asc" ? 1 : -1) || a.m.author.localeCompare(b.m.author),
  deaths: (a, b) => a.v.deaths - b.v.deaths,
  // the player's rating; mods not rated last, whichever way the column is sorted
  rating: (a, b, dir) => (!a.m.user.rating - !b.m.user.rating) * (dir === "asc" ? 1 : -1) ||
    (a.m.user.rating || 0) - (b.m.user.rating || 0),
  // Beginner to Grandmaster; mods without one last, whichever way the column is sorted
  difficulty: (a, b, dir) => (!diffRank(a.m) - !diffRank(b.m)) * (dir === "asc" ? 1 : -1) || diffRank(a.m) - diffRank(b.m),
  // the slot shown (All slots); mods not played in any slot last, whichever way the column is sorted
  slot: (a, b, dir) => (!a.v.slot - !b.v.slot) * (dir === "asc" ? 1 : -1) || Number(a.v.slot) - Number(b.v.slot),
  // in progress, then completed, then not started; within one status, the most sides cleared first
  status: (a, b, dir) => STATUS_RANK[pageStatus(a.v.status)] - STATUS_RANK[pageStatus(b.v.status)] ||
    (dir === "asc" ? -1 : 1) * SORTS.progress(a, b),
};
const diffRank = (m) => DIFFICULTIES.indexOf(m.user.difficulty) + 1;  // 0: not set (or an old free-text value)
const FIRST_DIR = { time: "desc", progress: "desc", name: "asc", author: "asc", deaths: "desc", rating: "desc", status: "asc", difficulty: "asc",
                    slot: "asc" };
const sortDir = () => state.dir || FIRST_DIR[state.sort];

const sorter = (key, dir) => (a, b) => (dir === "asc" ? 1 : -1) * SORTS[key](a, b, dir) || a.m.name.localeCompare(b.m.name);

function visibleMods() {
  const needle = state.q.trim().toLowerCase();
  return state.data.mods
    .map((m) => ({ m, v: viewOf(m) }))
    .filter(({ m, v }) => passes(m, v) && (!needle || index.search[m.id].includes(needle)))
    .sort(sorter(state.sort, sortDir()));
}

// ------------------------------------------------------------------ rendering

function bar(v) {
  // Sides cleared, in one color (docs/UI.md); hovering shows the count per side letter.
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
  if (!v.slot) return `<span class="num hide-sm"></span>`;
  const others = v.slots.filter((k) => k !== v.slot);
  const title = `Shown: slot ${v.slot}, your furthest` + (others.length ? `. Also played in slot${others.length > 1 ? "s" : ""} ${others.join(", ")}` : "");
  return `<span class="num hide-sm" title="${esc(title)}">${esc(v.slot)}</span>`;
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

// The columns after the arrow (docs/UI.md, "Columns"). Each has a width in px that the player can drag (the line
// at its right edge), as in Excel: the columns to its right move along, and the table scrolls sideways when it's
// wider than the window. The defaults fit the 1200px page with the columns shown at first. Every column but Mod can be
// hidden from the Columns menu. Best and Berries start hidden (user, 2026-10-07). Slot only shows with "All slots".
const COLUMNS = [
  { id: "mod", label: "Mod", sort: "name", what: "name", width: 230, min: 120 },
  { id: "author", label: "Author", sort: "author", width: 115, min: 60 },
  { id: "sides", label: "Sides", sort: "progress", what: "sides cleared", width: 180, min: 120 },
  { id: "deaths", label: "Deaths", sort: "deaths", width: 64, min: 48 },
  { id: "time", label: "Time", sort: "time", what: "time played", width: 72, min: 56 },
  { id: "best", label: "Best", help: "Best time, for a single side", width: 64, min: 48 },
  { id: "berries", label: "Berries", width: 60, min: 48 },
  { id: "checkpoint", label: "Checkpoint", help: "The last checkpoint reached, in a side not cleared yet", width: 130, min: 80 },
  { id: "rating", label: "Rating", sort: "rating", what: "your rating", help: "How much you enjoyed it, 1 to 5", width: 92, min: 92, mine: true },
  { id: "difficulty", label: "Difficulty", sort: "difficulty", what: "your difficulty", help: "How hard it is for you", width: 100, min: 72, mine: true },
  { id: "tags", label: "Tags", help: "Your tags", width: 150, min: 70, mine: true },
  { id: "note", label: "Note", help: "Your note: click one to write or change it", width: 100, min: 80, mine: true },
  { id: "slot", label: "Slot", sort: "slot", what: "slot shown", help: "The slot shown: your furthest", width: 44, min: 40 },
];
const DEFAULT_HIDDEN = ["best", "berries", "difficulty", "tags"];
// The columns there were before the page saved which ones it knew: a column added since starts as DEFAULT_HIDDEN says,
// even for a player whose saved settings don't mention it.
const OLD_COLUMNS = ["mod", "author", "sides", "deaths", "time", "best", "berries", "slot"];
const GAP = 12, ARROW = 16; // .mod-head's gap and arrow column, in style.css
let prefs = { hidden: DEFAULT_HIDDEN, widths: {}, auto: [] };  // auto: the player's columns that turned on by themselves

const colWidth = (c) => prefs.widths[c.id] || c.width;
const canShow = (c) => c.id !== "slot" || state.key === "all";
const shownCols = () => COLUMNS.filter((c) => c.id === "mod" || (canShow(c) && !prefs.hidden.includes(c.id)));

function applyColumns() {
  // The grid every row uses; rows inside an opened mod have no author, so their name takes its place too. The rows
  // are as wide as their columns (--row-w), so the table scrolls sideways when they don't fit.
  const cols = shownCols(), list = $("list").style;
  list.setProperty("--mod-cols", `${ARROW}px ` + cols.map((c) => `${colWidth(c)}px`).join(" "));
  list.setProperty("--row-w", `${2 * 14 + ARROW + GAP * cols.length + cols.reduce((a, c) => a + colWidth(c), 0)}px`);  // 14: .mod-head's padding
  list.setProperty("--name-span", cols.some((c) => c.id === "author") ? 2 : 1);
}

function cells(map) {
  // One cell per shown column, in order; a column missing from map (author, on rows inside a mod) is left out.
  return shownCols().filter((c) => c.id in map).map((c) => map[c.id]).join("");
}

async function loadPrefs() {
  try {
    const r = await fetch("/api/prefs");
    const p = r.ok ? await r.json() : {};
    const hidden = Array.isArray(p.hidden) ? p.hidden : DEFAULT_HIDDEN, known = Array.isArray(p.known) ? p.known : OLD_COLUMNS;
    prefs = { hidden: [...hidden, ...DEFAULT_HIDDEN.filter((id) => !known.includes(id) && !hidden.includes(id))],
              widths: p.widths && typeof p.widths === "object" ? p.widths : {}, auto: Array.isArray(p.auto) ? p.auto : [],
              export: p.export && typeof p.export === "object" ? p.export : undefined };
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

// ------------------------------------------------------------------ export (docs/features/export-csv-xlsx.md)

// The file's columns, as in export.py COLUMNS; page: the table column that ticks it at first. The server builds the
// file; the page sends every mod (search and filters don't apply), in the order picked here.
const EXPORT_COLUMNS = [
  { id: "mod", label: "Mod", page: "mod" },
  { id: "id", label: "Mod ID" },
  { id: "author", label: "Author", page: "author" },
  { id: "status", label: "Status", page: "sides" },
  { id: "sides_done", label: "Sides cleared", page: "sides" },
  { id: "sides_total", label: "Sides total", page: "sides" },
  { id: "deaths", label: "Deaths", page: "deaths" },
  { id: "time", label: "Time", page: "time" },
  { id: "best", label: "Best", page: "best" },
  { id: "berries", label: "Berries", page: "berries" },
  { id: "checkpoint", label: "Checkpoint", page: "checkpoint" },
  { id: "slot", label: "Slot", page: "slot" },
  { id: "rating", label: "Rating", page: "rating", mine: true },
  { id: "difficulty", label: "Difficulty", page: "difficulty", mine: true },
  { id: "tags", label: "Tags", page: "tags", mine: true },
  { id: "note", label: "Note", page: "note", mine: true },
];
const SORT_NAMES = { time: "Time played", progress: "Sides cleared", status: "Status", name: "Name", author: "Author",
                     deaths: "Deaths", rating: "Your rating", difficulty: "Your difficulty", slot: "Slot" };
// fmt and cols are kept with the page's settings once the player downloads; the sort starts as the table's.
const exp = { fmt: "csv", cols: [], sort: "time", dir: "desc" };

function openExport() {
  // Each time the panel opens: the table's sort, and the columns last exported (at first, the ones shown).
  const shown = shownCols().map((c) => c.id), saved = prefs.export || {};
  exp.fmt = saved.fmt === "xlsx" ? "xlsx" : "csv";
  exp.cols = Array.isArray(saved.cols) ? saved.cols.filter((id) => EXPORT_COLUMNS.some((c) => c.id === id))  // none from an older page
    : EXPORT_COLUMNS.filter((c) => shown.includes(c.page)).map((c) => c.id);
  // The table can still be sorted by Slot after picking one slot, where the panel doesn't offer it.
  const offered = state.sort !== "slot" || state.key === "all";
  exp.sort = offered ? state.sort : "time";
  exp.dir = offered ? sortDir() : FIRST_DIR.time;
  renderExport();
}

function renderExport() {
  const all = state.key === "all", n = state.data?.mods.length || 0;
  const box = (c) => {
    const off = c.id === "slot" && !all, on = c.id === "mod" || (exp.cols.includes(c.id) && !off);
    return `<label${off ? ' class="muted" title="Only with All slots"' : ""}><input type="checkbox" data-xcol="${c.id}"` +
      `${on ? " checked" : ""}${c.id === "mod" || off ? " disabled" : ""}> ${c.label}</label>`;
  };
  const fmt = (id, label) => `<button type="button" class="opt" data-xfmt="${id}" aria-pressed="${exp.fmt === id}">${label}</button>`;
  const words = exp.sort === "name" || exp.sort === "author" ? ["A to Z", "Z to A"]
    : exp.sort === "status" ? ["In progress first", "Not started first"] : ["Lowest first", "Highest first"];
  $("export").innerHTML = `
    <span class="lab">Format</span><div class="opts">${fmt("csv", "CSV")}${fmt("xlsx", "Excel")}</div>
    <span class="lab">Columns</span>
    <div class="xcols">
      <div>${EXPORT_COLUMNS.filter((c) => !c.mine).map(box).join("")}</div>
      <div><h4>Yours</h4>${EXPORT_COLUMNS.filter((c) => c.mine).map(box).join("")}</div>
    </div>
    <span class="lab">Sort by</span>
    <div class="opts">
      <select data-xsort aria-label="Sort by">${Object.entries(SORT_NAMES).filter(([k]) => k !== "slot" || all)
        .map(([k, label]) => `<option value="${k}"${k === exp.sort ? " selected" : ""}>${label}</option>`).join("")}</select>
      <select data-xdir aria-label="Order">${["asc", "desc"].map((d, i) =>
        `<option value="${d}"${d === exp.dir ? " selected" : ""}>${words[i]}</option>`).join("")}</select>
    </div>
    <hr>
    <div class="foot"><span id="export-msg">All ${fmtNum(n)} mods${all ? ", each from its furthest slot" : ` in slot ${esc(state.key)}`}.
      Search and filters don't apply.</span>
      <button type="button" class="primary" data-download>Download</button></div>`;
}

async function download() {
  const btn = document.querySelector("[data-download]"), msg = $("export-msg");
  const cols = ["mod", ...exp.cols.filter((c) => c !== "mod" && (c !== "slot" || state.key === "all"))];
  const ids = state.data.mods.map((m) => ({ m, v: viewOf(m) })).sort(sorter(exp.sort, exp.dir)).map(({ m }) => m.id);
  btn.disabled = true;
  try {
    const r = await fetch("/api/export", {
      method: "POST", headers: { "Content-Type": "application/json", "X-Celeste-Tracker": "1" },
      body: JSON.stringify({ fmt: exp.fmt, slot: state.key, cols, ids }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `the server answered ${r.status}`);
    const blob = await r.blob();
    const name = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") || "")?.[1] || `celeste-progress.${exp.fmt}`;
    prefs.export = { fmt: exp.fmt, cols: exp.cols };
    savePrefs();
    // The desktop window can't save a download itself: it asks where, and writes the file (desktop.py).
    const api = window.pywebview?.api;
    if (api?.save_file) {
      const where = await api.save_file(name, await base64(blob));
      if (!where) {  // the player cancelled the Save dialog: nothing was written, so the panel stays
        msg.textContent = "Not saved.";
        btn.disabled = false;
        return;
      }
      showNotice(`Saved <b>${esc(where)}</b>`);
    } else {
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
    }
    $("export-menu").open = false;
  } catch (e) {
    msg.textContent = `Couldn't export: ${e.message}`;
    msg.classList.add("error-text");
    btn.disabled = false;
  }
}

const base64 = (blob) => new Promise((ok, fail) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(",", 2)[1]);
  r.onerror = () => fail(r.error);
  r.readAsDataURL(blob);
});

function showNotice(html) {
  $("notice").innerHTML = `<span>${html}</span><button type="button" data-notice-ok>OK</button>`;
  $("notice").hidden = false;
}

function checkpointCell(v, where = "") {
  // The last checkpoint the save lists for the unfinished side played longest (rules.py); a side row has its own
  // list. Nothing once every side is cleared. The save lists checkpoints by room ID; the name comes from the mod.
  // where: under it, say which "chapter" and side, or only which "side", on rows with several of them.
  const lc = v.latest_checkpoint
    || (v.status === "in progress" && v.checkpoints?.length ? v.checkpoints[v.checkpoints.length - 1] : null);
  if (!lc) return `<span class="hide-sm"></span>`;
  const ch = lc.sid && index.chapterOfSid[lc.sid], chapter = ch ? ch.title || ch.sid.split("/").pop() : "";
  const at = [chapter, lc.side ? `${lc.side} side` : ""].filter(Boolean).join(", "), side = lc.side ? `${lc.side} side` : "";
  const tip = `${at ? `${at}: ` : ""}${lc.title || lc.room}${lc.title ? ` (room ${lc.room})` : ""}`;
  return `<span class="cpcell hide-sm" title="${esc(tip)}">${esc(lc.title || lc.room)}` +
    `${lc.title ? ` <span class="room">(${esc(lc.room)})</span>` : ""}` +
    `${where === "chapter" && at ? `<span class="sub">${esc(at)}</span>` : where === "side" && side ? `<span class="sub">${esc(side)}</span>` : ""}</span>`;
}

// The tree table (docs/UI.md, "Layout"): mods, level sets, chapters and sides are all rows of one grid with the
// same columns, indented by level. Only rows with something under them open.
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

function numbers(v, bestTime) {
  return {
    deaths: `<span class="num hide-sm">${dash(v, fmtNum(v.deaths))}</span>`,
    time: `<span class="num hide-sm">${dash(v, fmtTime(v.ticks))}</span>`,
    best: `<span class="num hide-sm">${bestTime}</span>`,
    berries: `<span class="num hide-sm">${dash(v, fmtNum(v.berries))}</span>`,
  };
}

function modCard({ m, v }) {
  const open = state.open.has(m.id);
  // The dim second line, as Olympus shows it: ID ∙ details (docs/UI.md, "What players already know").
  const sub = esc([m.id !== m.name ? m.id : "", m.sets.length > 1 ? `${m.sets.length} level sets` : ""]
    .filter(Boolean).join(" ∙ ")) + ownTags(m);
  const chs = chapters(m);
  return `<article class="mod${open ? " open" : ""}${m.user.dropped ? " dropped" : ""}" data-mod="${esc(m.id)}">
    <div class="mod-head" role="button" tabindex="0" aria-expanded="${open}">
      <span class="caret">▸</span>
      ${cells({
        mod: `<span class="name">${esc(m.name)}${sub ? `<span class="sub">${sub}</span>` : ""}</span>`,
        author: `<span class="author hide-sm" title="${esc(m.author ? `GameBanana author: ${m.author}` : "Not on GameBanana's mod list")}">${esc(m.author)}</span>`,
        sides: progress(v, q(m), !known(m)),
        ...numbers(v, chs.length === 1 ? best(chs[0]) : ""),
        checkpoint: checkpointCell(v, chs.length > 1 ? "chapter" : chs.length && countedSides(chs[0]).length > 1 ? "side" : ""),
        rating: stars(m, "row"),
        difficulty: `<span class="diff hide-sm">${esc(m.user.difficulty)}</span>`,
        tags: tagCell(m),
        // Clicking it opens the mod with the cursor in its note, so an empty one is how to write one.
        note: `<span class="notecell hide-sm" data-note-cell title="${esc(m.user.note || "Click to write a note")}">${esc(m.user.note)}</span>`,
        slot: slotCell(v),
      })}
    </div>
    ${open ? modBody(m, v) : ""}
  </article>`;
}

function modBody(m, v) {
  const facts = [`<span>Mod ID <b>${esc(m.id)}</b></span>`];
  if (m.gamebanana_title && m.gamebanana_title !== m.name) facts.push(`<span>GameBanana <b>${esc(m.gamebanana_title)}</b></span>`);
  facts.push(`<span>Hearts collected <b>${v.hearts}</b></span>`);
  if (state.key === "all" && v.slot) facts.push(`<span>${shownSlot(m, v)}</span>`);
  if (!known(m)) facts.push(`<span>Not in the Mods folder: only what you opened is listed</span>`);
  // Not on the row: on most rows, and it doesn't help pick what to play (user, 2026-10-08).
  if (!v.loaded) facts.push(`<span>Everest didn't load this mod the last time the game saved</span>`);
  return `<div class="mod-body">${guide({ kind: "mod", id: m.id, name: m.name })}<div class="facts">${facts.join("")}</div>${yours(m)}</div>` +
    modRows(m);
}

function setLabel(ls) {
  return ls.title || ls.name.split("/").pop(); // under its mod, the last part of the ID is enough ("0-Gyms")
}

function guide({ kind, id, name }, style = "") {
  // A thread line (style.css): clicking it closes the mod, level set or chapter it comes from.
  return `<span class="guide" data-close="${kind}" data-id="${esc(id)}" title="Close ${esc(name)}"${style}></span>`;
}

function treeRow(level, { attr = "", open = null, name, sub = "", strong = false, v, mark = "", bestTime = "", cpWhere = "", anc }) {
  // open: null = nothing under this row; true/false = it opens, and is open or not. anc: the rows above this one,
  // the mod first, each drawn as a thread line.
  const toggle = open !== null;
  return `<div class="trow${open ? " open" : ""}"${attr}${toggle ? ` role="button" tabindex="0" aria-expanded="${open}"` : ""}>
    ${guide(anc[0])}` + cells({
      mod: `<span class="tname${strong ? " strong" : ""}" style="--lvl:${level}">` +
        anc.slice(1).map((a, k) => guide(a, ` style="left:${k * 20 - 2}px"`)).join("") +
        `<span class="caret">${toggle ? "▸" : ""}</span>` +
        `<span class="t">${name}${sub ? `<small>${sub}</small>` : ""}</span></span>`,
      sides: progress(v, mark), ...numbers(v, bestTime), checkpoint: checkpointCell(v, cpWhere), rating: `<span class="hide-sm"></span>`, difficulty: `<span class="hide-sm"></span>`, tags: `<span class="hide-sm"></span>`, note: `<span class="hide-sm"></span>`,
      slot: `<span class="hide-sm"></span>`,
    }) + `</div>`;
}

function modRows(m) {
  const chs = chapters(m), anc = [{ kind: "mod", id: m.id, name: m.name }];
  if (chs.length === 1) { // a one-chapter mod: straight to its sides, or nothing more when it has one
    const sides = countedSides(chs[0]);
    return sides.length > 1 ? sides.map((s) => sideRow(s, 1, anc)).join("") : "";
  }
  if (m.sets.length === 1) return chapterRows(m, m.sets[0].chapters, 1, anc);
  return m.sets.map((ls) => {
    // A collab opens to its level sets (difficulty tiers); each tier opens to its chapters.
    const id = setId(m, ls), open = state.openSet.has(id);
    // Each in a group of its own, so an opened level set's row sticks only while its chapters are on screen.
    return `<div class="tgroup">` + treeRow(1, { attr: ` data-set="${esc(id)}"`, open, name: esc(setLabel(ls)), strong: true,
                        v: viewOf(ls), mark: q(m), cpWhere: ls.chapters.length > 1 ? "chapter" : "", anc }) +
      (open ? chapterRows(m, ls.chapters, 2, [...anc, { kind: "set", id, name: setLabel(ls) }]) : "") + `</div>`;
  }).join("");
}

const RANK = { "in progress": 0, completed: 1, "not opened": 2 };

function chapterRows(m, list, level, anc) {
  return [...list]
    .sort((a, b) => (RANK[viewOf(a, "not opened").status] ?? 3) - (RANK[viewOf(b, "not opened").status] ?? 3))
    .map((ch) => {
      const sides = countedSides(ch), many = sides.length > 1, open = many && state.openCh.has(ch.sid);
      const title = ch.title || ch.sid.split("/").pop();
      return treeRow(level, { attr: many ? ` data-ch="${esc(ch.sid)}"` : "", open: many ? open : null,
                              name: esc(title),
                              v: viewOf(ch, "not opened"), mark: q(m), bestTime: best(ch), cpWhere: many ? "side" : "", anc }) +
        (open ? sides.map((s) => sideRow(s, level + 1, [...anc, { kind: "ch", id: ch.sid, name: title }])).join("") : "");
    }).join("");
}

function sideRow(s, level, anc) {
  const v = sideView(s);
  return treeRow(level, { name: `${esc(s.side)} side`, v, bestTime: v.best_ticks ? fmtTime(v.best_ticks) : "-", anc });
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

// The Yours panel, in an opened mod: every field the player sets on it, in one place (docs/UI.md, "Your fields").
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
      <td class="num">${fmtNum(x.deaths)}</td>
      <td class="num">${v ? `${v.sides_done}/${v.sides_total}` : "-"}</td></tr>`;
  }).join("");
  el.innerHTML = `<details${open ? " open" : ""}><summary>Where you left off ` +
    `<span class="muted">Save &amp; Quit in ${slots.length} slot${slots.length > 1 ? "s" : ""}</span></summary>
    <table class="resume"><colgroup><col class="w-slot"><col><col><col class="w-side"><col><col><col class="w-deaths"><col class="w-n">
    </colgroup><thead><tr><th>Slot</th><th>Mod</th><th>Chapter</th><th>Side</th><th>Last checkpoint</th><th>Room</th>
    <th>Deaths this session</th><th>Sides</th></tr></thead><tbody>${rows}</tbody></table></details>`;
}

function renderSummary(rows) {
  const played = state.data.mods.map((m) => viewOf(m)).filter((v) => v.status !== "not started");
  const done = played.filter((v) => pageStatus(v.status) === "completed").length;
  const sides = played.reduce((a, v) => [a[0] + v.sides_done, a[1] + v.sides_total], [0, 0]);
  const fig = (label, n, of, unit = "") => `<span>${label} <b>${fmtNum(n)}</b>${of === undefined ? "" : ` of ${fmtNum(of)}${unit}`}</span>`;
  // "started": the list also has the installed mods never opened, so its total is bigger.
  $("summary").innerHTML = fig("Sides completed", sides[0], sides[1]) + fig("Mods completed", done, played.length, " started") +
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

// The header row over the mods (same grid as .mod-head). Click a column name to sort by it, again to flip it.
function listHead() {
  // Each column has a grip on its right edge: drag it to resize the column, double-click it for the default.
  const th = (c) => {
    const extra = c.id === "mod" || c.id === "sides" ? "" : " hide-sm";
    const grip = `<span class="grip" data-grip="${c.id}" title="Drag to resize, double-click for the default width"></span>`;
    if (!c.sort) return `<span class="th${extra}" role="columnheader"${c.help ? ` title="${esc(c.help)}"` : ""}>${grip}${c.label}</span>`;
    const on = state.sort === c.sort, dir = on ? sortDir() : FIRST_DIR[c.sort];
    const next = on ? (dir === "asc" ? "desc" : "asc") : dir;
    const icon = on ? (dir === "asc" ? "▲" : "▼") : "↕";
    return `<span class="th${extra}" role="columnheader"${on ? ` aria-sort="${dir}ending"` : ""}>${grip}` +
      `<button type="button" data-sort="${c.sort}" title="${c.help ? `${esc(c.help)}. ` : ""}Sort by ${c.what || c.id}, ${next === "asc" ? "lowest" : "highest"} first` +
      `${c.sort === "name" || c.sort === "author" ? (next === "asc" ? " (A to Z)" : " (Z to A)") : ""}">${c.label}` +
      `<span class="icon" aria-hidden="true">${icon}</span></button></span>`;
  };
  return `<div class="list-head" role="row"><span></span>${shownCols().map(th).join("")}</div>`;
}

// Pagination under the table: rows per page, the range shown, and the pages (first, last, and the ones around
// the current one).
function pager(total, pages) {
  const from = state.per ? (state.page - 1) * state.per + 1 : 1, to = state.per ? Math.min(total, state.page * state.per) : total;
  const per = [25, 50, 100, 0].map((n) => `<option value="${n}"${n === state.per ? " selected" : ""}>${n || "All"}</option>`).join("");
  const nums = [];
  for (let n = 1; n <= pages; n++) {
    if (n === 1 || n === pages || Math.abs(n - state.page) <= 1) nums.push(n);
    else if (nums[nums.length - 1] !== "…") nums.push("…");
  }
  const btn = (n, text, label, disabled = false) => `<button type="button" data-page="${n}" aria-label="${label}"` +
    `${n === state.page && text === String(n) ? ' aria-current="page"' : ""}${disabled ? " disabled" : ""}>${text}</button>`;
  return `<nav class="pager" aria-label="Pages">
    <label>Rows per page <select data-per>${per}</select></label>
    <span class="num">${fmtNum(from)}–${fmtNum(to)} of ${fmtNum(total)} mods</span>
    <span class="pages">${btn(state.page - 1, "‹ Previous", "Previous page", state.page <= 1)}` +
      nums.map((n) => (n === "…" ? `<span class="gap">…</span>` : btn(n, String(n), `Page ${n}`))).join("") +
      `${btn(state.page + 1, "Next ›", "Next page", state.page >= pages)}</span></nav>`;
}

function render() {
  if (!state.data) return;
  const rows = visibleMods();
  renderSummary(rows);
  renderFilters(rows);
  $("tag-list").innerHTML = allTags().map((t) => `<option value="${esc(t)}">`).join("");
  renderSessions();
  renderColumnsMenu();
  applyColumns();
  const pages = state.per ? Math.max(1, Math.ceil(rows.length / state.per)) : 1;
  state.page = Math.min(Math.max(1, state.page), pages);
  const shown = state.per ? rows.slice((state.page - 1) * state.per, state.page * state.per) : rows;
  $("list").innerHTML = rows.length ? listHead() + shown.map(modCard).join("") + (rows.length > 25 ? pager(rows.length, pages) : "")
    : `<div class="empty">No mods match. Clear the search${filtersOn().length ? ` or the filters` : ""}.</div>`;
  for (const area of document.querySelectorAll("[data-note]")) fitNote(area);
  measure();
  writeHash();
}

function measure() {
  // Where the sticky rows stop (style.css): under the header row, then under an opened mod's row.
  const root = document.documentElement.style;
  root.setProperty("--head-h", `${document.querySelector(".list-head")?.offsetHeight || 0}px`);
  for (const mod of document.querySelectorAll(".mod.open")) {
    mod.style.setProperty("--mh", `${mod.querySelector(".mod-head").offsetHeight}px`);
  }
}
window.addEventListener("resize", () => { if (state.data) applyColumns(); measure(); });

// ------------------------------------------------------------------ loading and editing

async function load(refresh = false) {
  try {
    const r = await fetch("/api/library" + (refresh ? "?refresh=1" : ""));
    if (!r.ok) throw new Error(`the server answered ${r.status}`);
    state.data = await r.json();
    buildIndex(state.data);
    fillSlots();
    $("error").hidden = true;
    render();
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
  buildIndex(state.data);  // the search matches notes
}

async function rate(group, n) {
  // A star clicked or chosen with the arrow keys; the same star again clears the rating. Focus stays on the stars.
  const key = group.dataset.key, where = group.dataset.where, m = state.data.mods.find((x) => x.id === key);
  const value = m.user.rating === n ? 0 : n;
  try { await save(key, "rating", value); } catch (e) { return alert(`Couldn't save your rating: ${e.message}`); }
  render();
  const again = document.querySelector(`.rate[data-key="${CSS.escape(key)}"][data-where="${where}"]`);
  again?.querySelector(`[data-rate="${value || n}"]`)?.focus();
}

// The first time the player sets a difficulty or adds a tag, that column turns on by itself, once, with a notice
// that says so (docs/UI.md, "Your fields"); hiding it again from the Columns menu sticks.
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
  render();
  document.querySelector(`.yours[data-key="${CSS.escape(key)}"] [data-difficulty]`)?.focus();
}

async function setTags(key, tags) {
  // Saves a mod's tags, then puts the cursor back in its "Add a tag" field.
  const clean = [...new Set(tags.map(cleanTag).filter(Boolean))].sort();
  try { await save(key, "tags", clean); } catch (e) { return alert(`Couldn't save the tags: ${e.message}`); }
  if (clean.length) firstUse("tags");
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
    // Once the player has left the panel, redraw so the note shows under the mod's name.
    if (!document.activeElement?.closest(".yours")) render();
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

function toggle(set, id) {
  set.has(id) ? set.delete(id) : set.add(id);
  render();
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

// ------------------------------------------------------------------ events

$("list").addEventListener("click", (e) => {
  const star = e.target.closest("[data-rate]");
  if (star) return rate(star.closest(".rate"), Number(star.dataset.rate));
  if (e.target.closest("[data-note-cell]")) return editNote(e.target.closest(".mod").dataset.mod);
  const untag = e.target.closest("[data-untag]");
  if (untag) {
    const key = untag.closest(".yours").dataset.key, m = state.data.mods.find((x) => x.id === key);
    return setTags(key, (m.user.tags || []).filter((t) => t !== untag.dataset.untag));
  }
  const sort = e.target.closest("[data-sort]");
  if (sort) {
    const key = sort.dataset.sort;
    state.dir = key === state.sort ? (sortDir() === "asc" ? "desc" : "asc") : "";
    state.sort = key;
    state.page = 1;
    return render();
  }
  const page = e.target.closest("[data-page]");
  if (page) {
    state.page = Number(page.dataset.page);
    render();
    return $("list").scrollTo({ top: 0 });
  }
  const line = e.target.closest(".guide");
  if (line) return closeFromLine(line);
  if (!e.target.closest("button, input, select, textarea, a")) openRow(e.target);
});

const SETS = { mod: () => state.open, set: () => state.openSet, ch: () => state.openCh };
const ROW = { mod: (id) => `.mod[data-mod="${id}"]`, set: (id) => `.trow[data-set="${id}"]`, ch: (id) => `.trow[data-ch="${id}"]` };

function closeFromLine(line) {
  // Clicking a thread line closes the row it comes from and, as on Reddit, brings that row back into view when
  // it was scrolled away.
  const { close: kind, id } = line.dataset;
  SETS[kind]().delete(id);
  render();
  const row = document.querySelector(ROW[kind](CSS.escape(id)));
  const top = $("list").getBoundingClientRect().top + (document.querySelector(".list-head")?.offsetHeight || 0);
  if (row && row.getBoundingClientRect().top < top) row.scrollIntoView({ block: "start" });
}

// Hovering a thread line lights up all of it, across the rows it runs through.
$("list").addEventListener("mouseover", (e) => {
  const line = e.target.closest(".guide");
  for (const g of document.querySelectorAll(".guide.hot")) g.classList.remove("hot");
  if (!line) return;
  const same = `.guide[data-close="${line.dataset.close}"][data-id="${CSS.escape(line.dataset.id)}"]`;
  for (const g of document.querySelectorAll(same)) g.classList.add("hot");
});

function openRow(target) {
  // A mod, level set or chapter row: open or close it. Returns false when the target isn't one.
  const head = target.closest(".mod-head"), set = target.closest(".trow[data-set]"), ch = target.closest(".trow[data-ch]");
  if (head) toggle(state.open, head.closest(".mod").dataset.mod);
  else if (set) toggle(state.openSet, set.dataset.set);
  else if (ch) toggle(state.openCh, ch.dataset.ch);
  return !!(head || set || ch);
}
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
  if ((e.key === "Enter" || e.key === " ") && e.target.matches("[role=button]") && openRow(e.target)) e.preventDefault();
});
$("list").addEventListener("change", (e) => {
  if (e.target.matches("[data-per]")) {
    state.per = Number(e.target.value);
    state.page = 1;
    return render();
  }
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

function editNote(id) {
  // A click in the Note column: open the mod, and put the cursor in its note.
  state.open.add(id);
  render();
  const area = document.querySelector(`.mod[data-mod="${CSS.escape(id)}"] [data-note]`);
  if (!area) return;
  area.focus({ preventScroll: true });
  area.closest(".yours").scrollIntoView({ block: "nearest" });
}
// Resizing a column, as in Excel: the grip on a column's right edge changes only that column's width, never below its
// minimum; the columns to its right move along.
const colOf = (id) => COLUMNS.find((c) => c.id === id);
$("list").addEventListener("pointerdown", (e) => {
  const grip = e.target.closest("[data-grip]");
  if (!grip || e.button !== 0) return;
  e.preventDefault();
  const c = colOf(grip.dataset.grip), x0 = e.clientX, w0 = colWidth(c);
  grip.setPointerCapture(e.pointerId);
  grip.classList.add("drag");
  document.body.classList.add("resizing");
  const move = (ev) => {
    prefs.widths = { ...prefs.widths, [c.id]: Math.round(Math.max(c.min, w0 + ev.clientX - x0)) };
    applyColumns();
  };
  const up = () => {
    grip.removeEventListener("pointermove", move);
    grip.classList.remove("drag");
    document.body.classList.remove("resizing");
    measure();
    savePrefs();
  };
  grip.addEventListener("pointermove", move);
  grip.addEventListener("pointerup", up, { once: true });
  grip.addEventListener("pointercancel", up, { once: true });
});
// Double-clicking a grip gives its column the default width.
$("list").addEventListener("dblclick", (e) => {
  const grip = e.target.closest("[data-grip]");
  if (!grip) return;
  const widths = { ...prefs.widths };
  delete widths[grip.dataset.grip];
  prefs.widths = widths;
  applyColumns();
  savePrefs();
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
  prefs = { hidden: DEFAULT_HIDDEN, widths: {}, auto: prefs.auto, export: prefs.export };
  savePrefs();
  render();
});
// The Export panel: drawn when it opens, and again when a choice changes what it offers.
$("export-menu").addEventListener("toggle", (e) => { if (e.target.open && state.data) openExport(); });
$("export").addEventListener("change", (e) => {
  const col = e.target.dataset.xcol;
  if (col) exp.cols = e.target.checked ? [...exp.cols, col] : exp.cols.filter((c) => c !== col);
  else if (e.target.matches("[data-xsort]")) { exp.sort = e.target.value; exp.dir = FIRST_DIR[exp.sort]; renderExport(); }
  else if (e.target.matches("[data-xdir]")) exp.dir = e.target.value;
});
$("export").addEventListener("click", (e) => {
  const fmt = e.target.closest("[data-xfmt]");
  if (fmt) { exp.fmt = fmt.dataset.xfmt; renderExport(); }
  if (e.target.closest("[data-download]")) download();
});
// The Columns, Filter and Export menus close on a click anywhere else, or Escape.
const MENUS = ["cols-menu", "filter-menu", "export-menu"];
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
  state.open.add(a.dataset.goto);
  state.q = "";
  $("q").value = "";
  const i = visibleMods().findIndex(({ m }) => m.id === a.dataset.goto);  // go to the page that has it
  if (i >= 0 && state.per) state.page = Math.floor(i / state.per) + 1;
  render();
  document.querySelector(`.mod[data-mod="${CSS.escape(a.dataset.goto)}"]`)?.scrollIntoView({ block: "start" });
});

let typingTimer;
$("q").addEventListener("input", (e) => {
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => { state.q = e.target.value; state.page = 1; render(); }, 150);
});
$("slot").addEventListener("change", (e) => { state.key = e.target.value; state.page = 1; render(); });
document.addEventListener("change", (e) => {
  if (!e.target.matches("[data-tagall]")) return;
  state.tagAll = e.target.value === "1";
  state.page = 1;
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
  state.page = 1;
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
