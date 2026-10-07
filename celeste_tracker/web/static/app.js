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
const sideStatus = (s) => (s.progress[state.key] ? s.progress[state.key].status : "not opened");

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

// The page shows three statuses for a mod or level set (doc/UI.md, "Statuses"): the server's "in progress" and
// "started" are both playing, and "all opened done" (a mod not in the Mods folder, every opened side cleared) is
// complete, with its totals marked "?". Sides: cleared, playing, not opened. The CLI and the JSON keep the
// server's words.
const PAGE_STATUS = { "in progress": "playing", started: "playing", "all opened done": "complete", completed: "cleared" };
const pageStatus = (s) => PAGE_STATUS[s] || s;
const STATUS_HELP = {
  playing: "Opened, not finished: some sides still to clear",
  complete: "Every side cleared",
  "not started": "Never opened",
  cleared: "This side is cleared",
  "not opened": "Never opened",
};
// Show filters by those statuses, so the menu and the Status column use the same words.
const FILTERS = {
  all: () => true,
  playing: (m, v) => pageStatus(v.status) === "playing",
  complete: (m, v) => pageStatus(v.status) === "complete",
  notstarted: (m, v) => v.status === "not started",
};
const OLD_SHOW = { played: "all", unfinished: "playing", dropped: "all" };  // bookmarks from before
const STATUS_RANK = { playing: 0, complete: 1, "not started": 2 };
// Sort keys, each comparing in ascending order; FIRST_DIR is the direction a column starts in when clicked
// (names A to Z, numbers high to low). Clicking the sorted column again flips it.
const SORTS = {
  time: (a, b) => a.v.ticks - b.v.ticks,
  progress: (a, b) => a.v.sides_done / (a.v.sides_total || 1) - b.v.sides_done / (b.v.sides_total || 1),
  name: (a, b) => a.m.name.localeCompare(b.m.name),
  deaths: (a, b) => a.v.deaths - b.v.deaths,
  rating: (a, b) => (a.m.user.rating || 0) - (b.m.user.rating || 0),
  // playing, then complete, then not started; within one status, the most sides cleared first
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

const label = pageStatus;

function status(s, unsure = false) {
  const st = pageStatus(s);
  const help = STATUS_HELP[st] + (unsure && st === "complete"
    ? ". This mod isn't in your Mods folder, so its real total is unknown: every side you opened is cleared" : "");
  return `<span class="status s-${cls(st)}" title="${esc(help)}">${esc(st)}</span>`;
}

function chip(s, heart = false) {
  const st = sideStatus(s);
  return `<span class="side-mark"><span class="chip c-${cls(st)}" title="${esc(s.side)} side: ${esc(label(st))}` +
    `${heart ? ", crystal heart collected" : ""}">${esc(s.side)}</span>` +
    (heart ? `<span class="heart" aria-hidden="true">♥</span>` : "") + `</span>`;
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
  if (!v.loaded) t.push(`<span class="tag" title="Everest didn't load this mod the last time the game saved">not loaded</span>`);
  return `<div class="tags">${t.join("")}</div>`;
}

function modCard({ m, v }) {
  const open = state.open.has(m.id);
  // The dim second line, as Olympus shows it: ID ∙ details (doc/UI.md, "What players already know").
  const sub = [m.id !== m.name ? m.id : "", m.sets.length > 1 ? `${m.sets.length} level sets` : ""]
    .filter(Boolean).join(" ∙ ");
  return `<article class="mod${open ? " open" : ""}${m.user.dropped ? " dropped" : ""}" data-mod="${esc(m.id)}">
    <div class="mod-head" role="button" tabindex="0" aria-expanded="${open}">
      <span class="caret">▸</span>
      <span class="name">${esc(m.name)}${sub ? `<span class="sub">${esc(sub)}</span>` : ""}</span>
      <span class="progress">${bar(v)}<small class="num">${v.sides_done}/${v.sides_total}${q(m)} sides</small></span>
      <span>${status(v.status, !known(m))}</span>
      <span class="num right hide-sm">${v.status === "not started" ? "-" : fmtNum(v.deaths)}</span>
      <span class="num right hide-sm">${v.status === "not started" ? "-" : fmtTime(v.ticks)}</span>
      <span class="hide-sm">${tags(m, v)}</span>
    </div>
    ${open ? modBody(m, v) : ""}
  </article>`;
}

function modBody(m, v) {
  const facts = [`<span>Mod ID <b>${esc(m.id)}</b></span>`];
  if (m.gamebanana_title && m.gamebanana_title !== m.name) facts.push(`<span>GameBanana <b>${esc(m.gamebanana_title)}</b></span>`);
  facts.push(`<span>Deaths <b>${v.deaths}</b></span>`, `<span>Berries <b>${v.berries}</b></span>`,
             `<span>Hearts collected <b>${v.hearts}</b></span>`);
  if (state.key === "all" && v.slot) facts.push(`<span>${shownSlot(m, v)}</span>`);
  if (!known(m)) facts.push(`<span>Not in the Mods folder: only what you opened is listed</span>`);
  const setNotes = m.sets.filter((s) => s.user.note).map((s) => `<div class="cps">${esc(s.title || s.name)}: ${esc(s.user.note)}</div>`);
  const body = m.sets.length > 1
    ? `<div class="sets">${m.sets.map((ls) => setBlock(m, ls)).join("")}</div>`
    : chaptersBlock(m, m.sets[0].chapters);
  return `<div class="mod-body">
    <div class="facts">${facts.join("")}</div>
    ${setNotes.join("")}
    ${body}
    ${SHOW_EDITOR ? mineEditor(m) : ""}
    <div class="legend"><span><span class="chip c-completed">A</span> cleared</span>
      <span><span class="chip c-in-progress">A</span> playing</span>
      <span><span class="chip c-not-opened">A</span> not opened</span>
      <span>♥ crystal heart collected (not needed to clear a side)</span></div>
  </div>`;
}

function setLabel(ls) {
  return ls.title || ls.name.split("/").pop(); // under its mod, the last part of the ID is enough ("0-Gyms")
}

function setBlock(m, ls) {
  // A collab opens to its level sets (difficulty tiers); each tier opens to its chapters.
  const v = viewOf(ls), id = setId(m, ls), open = state.openSet.has(id);
  return `<section class="set${open ? " open" : ""}">
    <div class="set-head" data-set="${esc(id)}" role="button" tabindex="0" aria-expanded="${open}">
      <span class="caret">▸</span><span class="set-name">${esc(setLabel(ls))}</span>
      <span class="progress">${bar(v)}<small class="num">${v.sides_done}/${v.sides_total}${q(m)} sides</small></span>
      ${status(v.status)}<span class="num right muted">${v.deaths} deaths</span>
      <span class="num right">${fmtTime(v.ticks)}</span></div>
    ${open ? chaptersBlock(m, ls.chapters) : ""}</section>`;
}

const RANK = { "in progress": 0, completed: 1, "not opened": 2 };

function chaptersBlock(m, list) {
  if (chapters(m).length === 1) return sideTable(list[0], false); // a one-chapter mod: straight to its sides
  const rows = [...list]
    .sort((a, b) => (RANK[viewOf(a, "not opened").status] ?? 3) - (RANK[viewOf(b, "not opened").status] ?? 3))
    .map((ch) => chapterRows(ch)).join("");
  return `<table class="chapters"><colgroup><col class="w-ch"><col class="w-sides"><col class="w-n"><col class="w-n">` +
         `<col></colgroup><thead><tr><th>Chapter</th><th>Sides</th><th class="right">Deaths</th>` +
         `<th class="right">Time</th><th>Latest checkpoint</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function chapterRows(ch) {
  const v = viewOf(ch, "not opened");
  const sides = countedSides(ch);
  const chips = sides.map((s) => chip(s, !!(s.progress[state.key] && s.progress[state.key].heart))).join("");
  const lc = v.latest_checkpoint;
  const open = state.openCh.has(ch.sid);
  const note = ch.user.note ? `<div class="cps">note: ${esc(ch.user.note)}</div>` : "";
  return `<tr class="chapter" data-ch="${esc(ch.sid)}" aria-expanded="${open}">
      <td>${esc(ch.title || ch.sid.split("/").pop())}${note}</td><td><div class="chips">${chips || "-"}</div></td>
      <td class="right num">${v.status === "not opened" ? "-" : v.deaths}</td>
      <td class="right num">${v.status === "not opened" ? "-" : fmtTime(v.ticks)}</td>
      <td class="cps">${lc ? esc(`${lc.side}: ${lc.title || lc.room}`) : ""}</td></tr>` +
    (open ? `<tr><td colspan="5">${sideTable(ch)}</td></tr>` : "");
}

function cps(list) {
  return list.length ? `${list.length}: ${list.map((c) => esc(c.title ? `${c.title} (${c.room})` : c.room)).join(", ")}` : "";
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

function sideTable(ch, berries = true) {
  // berries: false where the mod's facts line above already gives them (a one-chapter mod)
  const sides = countedSides(ch);
  if (sides.length === 1) return sideFacts(sides[0], berries);
  const rows = sides.map((s) => {
    const v = s.progress[state.key];
    return `<tr><td>${chip(s, !!(v && v.heart))}</td>
      <td>${status(sideStatus(s))}</td>
      <td class="right num">${v ? v.deaths : "-"}</td><td class="right num">${v ? fmtTime(v.ticks) : "-"}</td>
      <td class="right num">${v && v.best_ticks ? fmtTime(v.best_ticks) : "-"}</td>
      <td class="right num">${v ? v.berries : "-"}</td><td class="cps">${v ? cps(v.checkpoints) : ""}</td></tr>`;
  }).join("");
  return `<table class="sides"><colgroup><col class="w-side"><col class="w-status"><col class="w-n"><col class="w-n">` +
         `<col class="w-n"><col class="w-n"><col></colgroup><thead><tr><th>Side</th><th>Status</th>` +
         `<th class="right">Deaths</th><th class="right">Time</th><th class="right">Best</th>` +
         `<th class="right">Berries</th><th>Checkpoints reached</th></tr></thead>` +
         `<tbody>${rows || `<tr><td colspan="7" class="muted">Not opened in this slot</td></tr>`}</tbody></table>`;
}

function sideFacts(s, berries) {
  // A chapter with one side: its row already shows the side's chip, deaths and time, so only the rest is listed.
  const v = s.progress[state.key];
  if (!v) return `<div class="facts side-facts">Not opened in this slot</div>`;
  const facts = [`<span>Best <b>${v.best_ticks ? fmtTime(v.best_ticks) : "-"}</b></span>`];
  if (berries) facts.push(`<span>Berries <b>${v.berries}</b></span>`);
  const list = v.checkpoints.map((c) => esc(c.title ? `${c.title} (${c.room})` : c.room)).join(", ");
  facts.push(`<span>Checkpoints reached <b>${v.checkpoints.length}</b>${list ? `: ${list}` : ""}</span>`);
  return `<div class="facts side-facts">${facts.join("")}</div>`;
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
  const done = played.filter((v) => pageStatus(v.status) === "complete").length;
  const sides = played.reduce((a, v) => [a[0] + v.sides_done, a[1] + v.sides_total], [0, 0]);
  const fig = (label, n, of) => `<span>${label} <b>${fmtNum(n)}</b>${of === undefined ? "" : ` of ${fmtNum(of)}`}</span>`;
  $("summary").innerHTML = fig("Sides cleared", sides[0], sides[1]) + fig("Mods complete", done, played.length) +
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
    `${col("progress", "Sides", "", "sides cleared")}${col("status", "Status")}` +
    `${col("deaths", "Deaths", "right hide-sm")}${col("time", "Time", "right hide-sm", "time played")}` +
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
  writeHash();
}

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
  const head = e.target.closest(".mod-head");
  if (head) return toggle(state.open, head.closest(".mod").dataset.mod);
  const set = e.target.closest(".set-head");
  if (set) return toggle(state.openSet, set.dataset.set);
  const ch = e.target.closest("tr.chapter");
  if (ch) return toggle(state.openCh, ch.dataset.ch);
});
$("list").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const head = e.target.closest(".mod-head"), set = e.target.closest(".set-head");
  if (head) { e.preventDefault(); toggle(state.open, head.closest(".mod").dataset.mod); }
  else if (set) { e.preventDefault(); toggle(state.openSet, set.dataset.set); }
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
$("show").addEventListener("change", (e) => { state.show = e.target.value; state.page = 1; render(); });
$("refresh").addEventListener("click", () => load(true));

readHash();
$("q").value = state.q;
$("show").value = state.show;
load();
setInterval(poll, 5000);
