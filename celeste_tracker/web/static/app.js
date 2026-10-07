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
const state = { data: null, key: "all", show: "all", sort: "time", dir: "", page: 1, per: PER_PAGE, q: "", open: new Set(), openSet: new Set(),
                openCh: new Set() };
const setId = (m, ls) => `${m.id}/${ls.name}`; // a level set can be split across mods (Glyph + Glyph D side)
let index = { modOfSid: {}, search: {} };
let sessionsOpen = null; // the player's choice once they open or close the panel

// ------------------------------------------------------------------ URL hash

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.key = p.get("slot") || "all";
  state.show = FILTERS[p.get("show")] ? p.get("show") : (OLD_SHOW[p.get("show")] || "all");
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
  if (state.show !== "all") p.set("show", state.show);
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
  index = { modOfSid: {}, search: {} };
  for (const m of data.mods) {
    const words = [m.name, m.id, m.gamebanana_title];
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
// Show filters by those statuses, so the menu and the Status column use the same words. The values (playing,
// complete) are older names, kept so bookmarks still work.
const FILTERS = {
  all: () => true,
  playing: (m, v) => pageStatus(v.status) === "in progress",
  complete: (m, v) => pageStatus(v.status) === "completed",
  notstarted: (m, v) => v.status === "not started",
};
const OLD_SHOW = { played: "all", unfinished: "playing", dropped: "all" };  // bookmarks from before
const STATUS_RANK = { "in progress": 0, completed: 1, "not started": 2 };
// Sort keys, each comparing in ascending order; FIRST_DIR is the direction a column starts in when clicked
// (names A to Z, numbers high to low). Clicking the sorted column again flips it.
const SORTS = {
  time: (a, b) => a.v.ticks - b.v.ticks,
  progress: (a, b) => a.v.sides_done / (a.v.sides_total || 1) - b.v.sides_done / (b.v.sides_total || 1),
  name: (a, b) => a.m.name.localeCompare(b.m.name),
  deaths: (a, b) => a.v.deaths - b.v.deaths,
  rating: (a, b) => (a.m.user.rating || 0) - (b.m.user.rating || 0),
  // in progress, then completed, then not started; within one status, the most sides cleared first
  status: (a, b) => STATUS_RANK[pageStatus(a.v.status)] - STATUS_RANK[pageStatus(b.v.status)] ||
    (sortDir() === "asc" ? -1 : 1) * SORTS.progress(a, b),
};
const FIRST_DIR = { time: "desc", progress: "desc", name: "asc", deaths: "desc", rating: "desc", status: "asc" };
const sortDir = () => state.dir || FIRST_DIR[state.sort];

function visibleMods() {
  const needle = state.q.trim().toLowerCase();
  return state.data.mods
    .map((m) => ({ m, v: viewOf(m) }))
    .filter(({ m, v }) => FILTERS[state.show](m, v) && (!needle || index.search[m.id].includes(needle)))
    .sort((a, b) => (sortDir() === "asc" ? 1 : -1) * SORTS[state.sort](a, b) || a.m.name.localeCompare(b.m.name));
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

function tags(m, v) {
  const t = [];
  if (state.key === "all" && v.slot) {
    // All slots: the row shows one slot, the mod's furthest (rules.py); "(+2)" = also played in 2 other slots.
    const others = v.slots.filter((k) => k !== v.slot);
    const title = `Shown: slot ${v.slot}, your furthest` + (others.length ? `. Also played in slot${others.length > 1 ? "s" : ""} ${others.join(", ")}` : "");
    t.push(`<span class="tag" title="${esc(title)}">slot ${esc(v.slot)}${others.length ? ` (+${others.length})` : ""}</span>`);
  }
  if (m.user.rating) t.push(`<span class="tag own">${"★".repeat(m.user.rating)}</span>`);
  if (m.user.difficulty) t.push(`<span class="tag own">${esc(m.user.difficulty)}</span>`);
  if (m.user.dropped) t.push(`<span class="tag own">dropped</span>`);
  return `<div class="tags">${t.join("")}</div>`;
}

// The tree table (doc/UI.md, "Layout"): mods, level sets, chapters and sides are all rows of one grid with the
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

// The Best and Berries columns are hidden for now, at the user's request (2026-10-07).
const SHOW_BEST_BERRIES = false;

function numbers(v, bestTime) {
  return `<span class="num right hide-sm">${dash(v, fmtNum(v.deaths))}</span>
    <span class="num right hide-sm">${dash(v, fmtTime(v.ticks))}</span>` + (SHOW_BEST_BERRIES ?
    `<span class="num right hide-sm">${bestTime}</span>
    <span class="num right hide-sm">${dash(v, fmtNum(v.berries))}</span>` : "");
}

function modCard({ m, v }) {
  // A row of the list; clicking it opens the mod's card (cardHtml) in front of the list.
  // The dim second line, as Olympus shows it: ID ∙ details (doc/UI.md, "What players already know").
  const sub = [m.id !== m.name ? m.id : "", m.sets.length > 1 ? `${m.sets.length} level sets` : ""]
    .filter(Boolean).join(" ∙ ");
  const chs = chapters(m);
  return `<article class="mod${m.user.dropped ? " dropped" : ""}" data-mod="${esc(m.id)}">
    <div class="mod-head" role="button" tabindex="0" aria-haspopup="dialog">
      <span class="caret"></span>
      <span class="name">${esc(m.name)}${sub ? `<span class="sub">${esc(sub)}</span>` : ""}</span>
      ${progress(v, q(m), !known(m))}
      ${numbers(v, chs.length === 1 ? best(chs[0]) : "")}
      <span class="hide-sm">${tags(m, v)}</span>
    </div>
  </article>`;
}


function setLabel(ls) {
  return ls.title || ls.name.split("/").pop(); // under its mod, the last part of the ID is enough ("0-Gyms")
}

function guide({ kind, id, name }, style = "") {
  // A thread line (style.css): clicking it closes the mod, level set or chapter it comes from.
  return `<span class="guide" data-close="${kind}" data-id="${esc(id)}" title="Close ${esc(name)}"${style}></span>`;
}

function treeRow(level, { attr = "", open = null, name, sub = "", strong = false, v, mark = "", bestTime = "", anc }) {
  // open: null = nothing under this row; true/false = it opens, and is open or not. anc: the rows above this one,
  // the mod first, each drawn as a thread line.
  const toggle = open !== null;
  return `<div class="trow${open ? " open" : ""}"${attr}${toggle ? ` role="button" tabindex="0" aria-expanded="${open}"` : ""}>
    ${anc[0] ? guide(anc[0]) : "<span></span>"}
    <span class="tname${strong ? " strong" : ""}" style="--lvl:${level}">` +
    anc.slice(1).map((a, k) => guide(a, ` style="left:${k * 20 - 2}px"`)).join("") +
    `<span class="caret">${toggle ? "▸" : ""}</span>` +
    `<span class="t">${name}${sub ? `<small>${sub}</small>` : ""}</span></span>
    ${progress(v, mark)}${numbers(v, bestTime)}<span class="hide-sm"></span></div>`;
}

function modRows(m) {
  const chs = chapters(m), anc = [null]; // in the card, the mod itself has no thread line
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
                        sub: ls.user.note ? `note: ${esc(ls.user.note)}` : "", v: viewOf(ls), mark: q(m), anc }) +
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
                              name: esc(title), sub: ch.user.note ? `note: ${esc(ch.user.note)}` : "",
                              v: viewOf(ch, "not opened"), mark: q(m), bestTime: best(ch), anc }) +
        (open ? sides.map((s) => sideRow(s, level + 1, [...anc, { kind: "ch", id: ch.sid, name: title }])).join("") : "");
    }).join("");
}

function sideRow(s, level, anc) {
  const v = sideView(s);
  return treeRow(level, { name: `${esc(s.side)} side`, v, bestTime: v.best_ticks ? fmtTime(v.best_ticks) : "-", anc });
}


// The player's own fields (rating, difficulty, dropped, rename, note) are hidden on the page for now, at the
// user's request (2026-10-05); the CLI still edits them, and the tags column still shows what's set.
const SHOW_EDITOR = false;

function mineEditor(m) {
  const u = m.user;
  const stars = [1, 2, 3, 4, 5].map((n) =>
    `<button type="button" data-rate="${n}" class="${(u.rating || 0) >= n ? "on" : ""}" aria-label="${n} of 5">★</button>`).join("");
  return `<div class="mine" data-key="${esc(m.id)}">
    <label>Rating</label><div class="stars">${stars} <span class="saved" hidden>saved</span></div>
    <label for="d-${esc(m.id)}">Difficulty</label>
    <input id="d-${esc(m.id)}" type="text" data-field="difficulty" value="${esc(u.difficulty)}" placeholder="e.g. Expert, GM+1">
    <label>Dropped</label><label><input type="checkbox" data-field="dropped" ${u.dropped ? "checked" : ""}> I gave up on this one</label>
    <label for="r-${esc(m.id)}">My name for it</label>
    <input id="r-${esc(m.id)}" type="text" data-field="rename" value="${esc(u.rename)}" placeholder="${esc(m.gamebanana_title || m.name)}">
    <label for="n-${esc(m.id)}">Note</label>
    <textarea id="n-${esc(m.id)}" data-field="note" placeholder="e.g. stopped at the ice part">${esc(u.note)}</textarea>
  </div>`;
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

function renderSummary(rows) {
  const played = state.data.mods.map((m) => viewOf(m)).filter((v) => v.status !== "not started");
  const done = played.filter((v) => pageStatus(v.status) === "completed").length;
  const sides = played.reduce((a, v) => [a[0] + v.sides_done, a[1] + v.sides_total], [0, 0]);
  const fig = (label, n, of) => `<span>${label} <b>${fmtNum(n)}</b>${of === undefined ? "" : ` of ${fmtNum(of)}`}</span>`;
  $("summary").innerHTML = fig("Sides completed", sides[0], sides[1]) + fig("Mods completed", done, played.length) +
    (state.show !== "all" || state.q.trim() ? fig("Showing", rows.length) : "");
  // Each Show option with how many mods it has in this slot.
  const all = state.data.mods.map((m) => ({ m, v: viewOf(m) }));
  for (const o of $("show").options) {
    o.textContent = `${o.dataset.label} (${all.filter(({ m, v }) => FILTERS[o.value](m, v)).length})`;
  }
}

// The header row over the mods (same grid as .mod-head). Click a column name to sort by it, again to flip it.
function listHead() {
  const col = (sort, text, extra = "", what = text.toLowerCase()) => {
    const on = state.sort === sort, dir = on ? sortDir() : FIRST_DIR[sort];
    const next = on ? (dir === "asc" ? "desc" : "asc") : dir;
    const icon = on ? (dir === "asc" ? "▲" : "▼") : "↕";
    return `<span class="th ${extra}" role="columnheader"${on ? ` aria-sort="${dir}ending"` : ""}>` +
      `<button type="button" data-sort="${sort}" title="Sort by ${what}, ${next === "asc" ? "lowest" : "highest"} first` +
      `${sort === "name" ? (next === "asc" ? " (A to Z)" : " (Z to A)") : ""}">${text}` +
      `<span class="icon" aria-hidden="true">${icon}</span></button></span>`;
  };
  return `<div class="list-head" role="row"><span></span>${col("name", "Mod", "", "name")}` +
    `${col("progress", "Sides", "", "sides cleared")}` +
    `${col("deaths", "Deaths", "right hide-sm")}${col("time", "Time", "right hide-sm", "time played")}` +
    (SHOW_BEST_BERRIES ? `<span class="th right hide-sm" title="Best time, for a single side">Best</span>` +
      `<span class="th right hide-sm">Berries</span>` : "") +
    `${col("rating", "Slots and tags", "right hide-sm", "your rating")}</div>`;
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
  renderSessions();
  const pages = state.per ? Math.max(1, Math.ceil(rows.length / state.per)) : 1;
  state.page = Math.min(Math.max(1, state.page), pages);
  const shown = state.per ? rows.slice((state.page - 1) * state.per, state.page * state.per) : rows;
  $("list").innerHTML = rows.length ? listHead() + shown.map(modCard).join("") + (rows.length > 25 ? pager(rows.length, pages) : "")
    : `<div class="empty">No mods match. Clear the search or pick "All mods" under Show.</div>`;
  $("list").classList.toggle("more-cols", SHOW_BEST_BERRIES);
  renderCard();
  measure();
  writeHash();
}

// ------------------------------------------------------------------ the mod card

const cardMod = () => state.data.mods.find((m) => m.id === [...state.open][0]);

function renderCard() {
  // Clicking a mod opens one card in front of the list (a modal <dialog>): everything about the mod, then its level
  // sets, chapters and sides as rows. It's in the URL as open=<mod id>, so it can be bookmarked.
  const dlg = $("card"), m = cardMod();
  if (!m) {
    if (dlg.open) dlg.close();
    return;
  }
  const body = dlg.querySelector(".card-body"), scroll = body && dlg.dataset.mod === m.id ? body.scrollTop : 0;
  dlg.dataset.mod = m.id;
  dlg.innerHTML = cardHtml(m, viewOf(m));
  dlg.querySelector(".card-body").scrollTop = scroll; // a re-render (a row opened, the game saved) keeps the place
  if (!dlg.open) dlg.showModal();
}

function cardHtml(m, v) {
  const sub = [m.id !== m.name ? m.id : "", m.gamebanana_title && m.gamebanana_title !== m.name ? `GameBanana: ${m.gamebanana_title}` : ""]
    .filter(Boolean).map(esc).join(" ∙ ");
  const fig = (label, value) => `<div class="fig"><span>${label}</span><b class="num">${value}</b></div>`;
  const played = !notPlayed(v);
  const figs = [fig("Deaths", played ? fmtNum(v.deaths) : "–"), fig("Time", played ? fmtTime(v.ticks) : "–"),
                fig("Hearts", fmtNum(v.hearts)), fig("Berries", played ? fmtNum(v.berries) : "–")];
  // Sides per letter, each with its own bar ("B sides 5/10"); with only A sides, the big bar already says it.
  const bySide = Object.entries(v.by_side || {});
  const letters = bySide.length < 2 ? "" : bySide.map(([k, [d, t]]) =>
    `<div class="letter"><span>${esc(k)} sides</span>${bar({ sides_done: d, sides_total: t })}<span class="num">${d}/${t}</span></div>`).join("");
  const notes = [];
  if (!known(m)) notes.push("Not in the Mods folder: only what you opened is listed, so the totals may be higher.");
  if (!v.loaded) notes.push("Everest didn't load this mod the last time the game saved.");
  if (m.user.note) notes.push(`Your note: ${esc(m.user.note)}`);
  return `<header class="card-head">
      <div class="card-title"><h2 id="card-title">${esc(m.name)}</h2>${sub ? `<p class="sub">${sub}</p>` : ""}</div>
      <span class="tags">${tags(m, v)}</span>
      <button type="button" class="card-close" data-close-card aria-label="Close" title="Close (Esc)">✕</button>
    </header>
    <div class="card-body">
      <section class="card-sum">
        <div class="card-progress">${progress(v, q(m), !known(m))}</div>
        <div class="figs">${figs.join("")}</div>
        ${letters ? `<div class="letters">${letters}</div>` : ""}
        ${SHOW_EDITOR ? mineEditor(m) : ""}
        ${notes.length ? `<ul class="notes">${notes.map((n) => `<li>${n}</li>`).join("")}</ul>` : ""}
      </section>
      ${slotTable(m, v)}
      <section class="card-tree">
        <div class="list-head card-cols" role="row"><span></span><span>${m.sets.length > 1 ? "Level set" : "Chapter"}</span>
          <span>Sides</span><span class="right">Deaths</span><span class="right">Time</span><span></span></div>
        ${modRows(m) || cardOneChapter(m)}
      </section>
    </div>`;
}

function cardOneChapter(m) {
  // A mod of one chapter with one side has no rows under it: say so instead of an empty table.
  return `<p class="muted card-empty">One chapter, one side: everything is above.</p>`;
}

function slotTable(m, v) {
  // Every slot the mod was played in, the one shown first; clicking a slot shows the whole page for that slot.
  if (state.key !== "all" || v.slots.length < 2) return "";
  const rows = [v.slot, ...v.slots.filter((k) => k !== v.slot)].map((k) => {
    const p = m.progress[k];
    return `<tr data-slot="${esc(k)}" title="Show slot ${esc(k)}"><td class="num">Slot ${esc(k)}${k === v.slot ? ' <span class="muted">shown, your furthest</span>' : ""}</td>
      <td class="num right">${p.sides_done}/${p.sides_total}</td><td class="num right">${fmtNum(p.deaths)}</td>
      <td class="num right">${fmtTime(p.ticks)}</td></tr>`;
  }).join("");
  return `<section class="card-slots"><h3>Played in ${v.slots.length} slots</h3><table><thead><tr><th>Slot</th>
    <th class="right">Sides</th><th class="right">Deaths</th><th class="right">Time</th></tr></thead><tbody>${rows}</tbody></table></section>`;
}

function measure() {
  // Where the sticky rows stop (style.css): under the top bar, then the header row, then an opened mod's row.
  const root = document.documentElement.style;
  root.setProperty("--top-h", `${document.querySelector(".top").offsetHeight}px`);
  root.setProperty("--head-h", `${document.querySelector(".list-head")?.offsetHeight || 0}px`);
  for (const mod of document.querySelectorAll(".mod.open")) {
    mod.style.setProperty("--mh", `${mod.querySelector(".mod-head").offsetHeight}px`);
  }
}
window.addEventListener("resize", measure);

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

async function save(key, field, value, el) {
  const r = await fetch("/api/user", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Celeste-Tracker": "1" },
    body: JSON.stringify({ key, field, value }),
  });
  if (!r.ok) { alert(`Couldn't save: ${(await r.json()).error || r.status}`); return; }
  await load();
  const saved = document.querySelector(`.mine[data-key="${CSS.escape(key)}"] .saved`);
  if (saved) { saved.hidden = false; setTimeout(() => (saved.hidden = true), 1500); }
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
    const typing = document.activeElement && document.activeElement.closest(".mine");
    if (state.data && version !== state.data.version && !typing) await load();
  } catch {
    $("live").classList.remove("on");
  }
}

// ------------------------------------------------------------------ events

$("list").addEventListener("click", (e) => {
  const rate = e.target.closest("[data-rate]");
  if (rate) {
    const key = rate.closest(".mine").dataset.key, n = Number(rate.dataset.rate);
    const m = state.data.mods.find((x) => x.id === key);
    return save(key, "rating", m.user.rating === n ? 0 : n); // clicking the current rating clears it
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
    return $("list").scrollIntoView({ block: "start" });
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
  const top = document.querySelector(".top").offsetHeight + (document.querySelector(".list-head")?.offsetHeight || 0);
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

function openCard(id) {
  state.open = new Set([id]);
  render();
}

function closeCard() {
  if (!state.open.size) return;
  state.open.clear();
  render();
}

function openRow(target) {
  // A mod, level set or chapter row: open or close it. Returns false when the target isn't one.
  const head = target.closest(".mod-head"), set = target.closest(".trow[data-set]"), ch = target.closest(".trow[data-ch]");
  if (head) openCard(head.closest(".mod").dataset.mod);
  else if (set) toggle(state.openSet, set.dataset.set);
  else if (ch) toggle(state.openCh, ch.dataset.ch);
  return !!(head || set || ch);
}
$("list").addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches("[role=button]") && openRow(e.target)) e.preventDefault();
});
$("list").addEventListener("change", (e) => {
  if (e.target.matches("[data-per]")) {
    state.per = Number(e.target.value);
    state.page = 1;
    return render();
  }
  const f = e.target.dataset.field;
  if (!f) return;
  const key = e.target.closest(".mine").dataset.key;
  save(key, f, e.target.type === "checkbox" ? e.target.checked : e.target.value, e.target);
});
// The card: rows open and thread lines close as in the list; Esc, ✕ or a click outside the card closes it.
$("card").addEventListener("click", (e) => {
  if (e.target === $("card") || e.target.closest("[data-close-card]")) return $("card").close();
  const slot = e.target.closest("[data-slot]");
  if (slot) {
    state.key = slot.dataset.slot;
    $("slot").value = state.key;
    return render();
  }
  const line = e.target.closest(".guide");
  if (line) return closeFromLine(line);
  openRow(e.target);
});
$("card").addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches("[role=button]") && openRow(e.target)) e.preventDefault();
});
$("card").addEventListener("close", closeCard);
$("card").addEventListener("mouseover", (e) => {
  const line = e.target.closest(".guide");
  for (const g of document.querySelectorAll(".guide.hot")) g.classList.remove("hot");
  if (!line) return;
  const same = `.guide[data-close="${line.dataset.close}"][data-id="${CSS.escape(line.dataset.id)}"]`;
  for (const g of document.querySelectorAll(same)) g.classList.add("hot");
});
$("sessions").addEventListener("toggle", (e) => { sessionsOpen = e.target.open; }, true);
$("sessions").addEventListener("click", (e) => {
  const a = e.target.closest("[data-goto]");
  if (a) openCard(a.dataset.goto);
});

let typingTimer;
$("q").addEventListener("input", (e) => {
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => { state.q = e.target.value; state.page = 1; render(); }, 150);
});
$("slot").addEventListener("change", (e) => { state.key = e.target.value; state.page = 1; render(); });
$("show").addEventListener("change", (e) => { state.show = e.target.value; state.page = 1; render(); });
$("refresh").addEventListener("click", () => load(true));
// "/" jumps to the search, as on GitHub and YouTube, unless the player is typing somewhere already.
document.addEventListener("keydown", (e) => {
  if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, textarea, select")) return;
  if ($("card").open) $("card").close(); // the search is behind the card
  e.preventDefault();
  $("q").focus();
  $("q").select();
});

readHash();
$("q").value = state.q;
$("show").value = state.show;
load();
setInterval(poll, 5000);
