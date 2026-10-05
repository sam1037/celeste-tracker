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

const state = { data: null, key: "all", show: "played", sort: "time", q: "", open: new Set(), openSet: new Set(),
                openCh: new Set() };
const setId = (m, ls) => `${m.id}/${ls.name}`; // a level set can be split across mods (Glyph + Glyph D side)
let index = { modOfSid: {}, search: {} };
let sessionsOpen = null; // the player's choice once they open or close the panel

// ------------------------------------------------------------------ URL hash

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.key = p.get("slot") || "all";
  state.show = p.get("show") || "played";
  state.sort = p.get("sort") || "time";
  state.q = p.get("q") || "";
  state.open = new Set((p.get("open") || "").split(SEP).filter(Boolean));
  state.openSet = new Set((p.get("sets") || "").split(SEP).filter(Boolean));
  state.openCh = new Set((p.get("ch") || "").split(SEP).filter(Boolean));
}

function writeHash() {
  const p = new URLSearchParams();
  if (state.key !== "all") p.set("slot", state.key);
  if (state.show !== "played") p.set("show", state.show);
  if (state.sort !== "time") p.set("sort", state.sort);
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

const UNFINISHED = new Set(["in progress", "started"]);
const COMPLETE = new Set(["complete", "all opened done"]);
const FILTERS = {
  played: (m, v) => v.status !== "not started",
  unfinished: (m, v) => UNFINISHED.has(v.status) && !m.user.dropped,
  complete: (m, v) => COMPLETE.has(v.status),
  notstarted: (m, v) => v.status === "not started",
  dropped: (m) => !!m.user.dropped,
  all: () => true,
};
const SORTS = {
  time: (a, b) => b.v.ticks - a.v.ticks,
  progress: (a, b) => b.v.sides_done / (b.v.sides_total || 1) - a.v.sides_done / (a.v.sides_total || 1),
  name: () => 0,
  deaths: (a, b) => b.v.deaths - a.v.deaths,
  rating: (a, b) => (b.m.user.rating || 0) - (a.m.user.rating || 0),
};

function visibleMods() {
  const needle = state.q.trim().toLowerCase();
  return state.data.mods
    .map((m) => ({ m, v: viewOf(m) }))
    .filter(({ m, v }) => FILTERS[state.show](m, v) && (!needle || index.search[m.id].includes(needle)))
    .sort((a, b) => SORTS[state.sort](a, b) || a.m.name.localeCompare(b.m.name));
}

// ------------------------------------------------------------------ rendering

function strip(v) {
  // The A | B | C strip (doc/UI.md): one portion per side letter, sized by its share of the sides.
  const parts = Object.entries(v.by_side || {});
  const title = parts.map(([k, [d, t]]) => `${k} sides: ${d} of ${t} cleared`).join("\n");
  return `<div class="strip" title="${esc(title)}">${parts.map(([k, [d, t]]) =>
    `<span class="seg side-${cls(k)}" style="flex-grow:${t}"><i style="width:${(100 * d) / (t || 1)}%"></i></span>`)
    .join("")}</div>`;
}

// The page's words for the server's statuses (doc/UI.md, principle 2); the CLI and JSON keep their own.
const LABELS = { "in progress": "playing", completed: "cleared" };
const label = (s) => LABELS[s] || s;

function status(s) {
  return `<span class="status s-${cls(s)}">${esc(label(s))}</span>`;
}

function chip(s, heart = false) {
  const st = sideStatus(s);
  return `<span class="chip side-${cls(s.side)} c-${cls(st)}" title="${esc(s.side)} side: ${esc(label(st))}` +
    `${heart ? ", crystal heart collected" : ""}">${esc(s.side)}</span>` +
    (heart ? `<span class="heart side-${cls(s.side)}" aria-hidden="true">♥</span>` : "");
}

function tags(m, v) {
  const t = [];
  if (state.key === "all" && v.slots.length) {
    const label = v.slots.length > 4 ? `${v.slots.length} slots` : `slot ${v.slots.join(",")}`;
    t.push(`<span class="tag" title="Played in slot ${esc(v.slots.join(", "))}">${esc(label)}</span>`);
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
      <span class="progress">${strip(v)}<small class="num"><span>${v.sides_done}/${v.sides_total}${q(m)} sides</span>` +
        `<span>${v.maps_done}/${v.maps_total}${q(m)} chapters</span></small></span>
      <span>${status(v.status)}</span>
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
  if (state.key === "all" && v.slots.length) facts.push(`<span>Slots <b>${esc(v.slots.join(", "))}</b></span>`);
  if (!known(m)) facts.push(`<span>Not in the Mods folder: only what you opened is listed</span>`);
  const setNotes = m.sets.filter((s) => s.user.note).map((s) => `<div class="cps">${esc(s.title || s.name)}: ${esc(s.user.note)}</div>`);
  const body = m.sets.length > 1
    ? `<div class="sets">${m.sets.map((ls) => setBlock(m, ls)).join("")}</div>`
    : chaptersBlock(m, m.sets[0].chapters);
  return `<div class="mod-body">
    <div class="facts">${facts.join("")}</div>
    ${setNotes.join("")}
    ${body}
    ${mineEditor(m)}
    <div class="legend"><span><span class="chip side-a c-completed">A</span> cleared</span>
      <span><span class="chip side-a c-in-progress">A</span> playing</span>
      <span><span class="chip side-a c-not-opened">A</span> not opened</span>
      <span>Blue, red and gold are the A, B and C sides, as in the game</span>
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
      <span class="progress">${strip(v)}<small class="num">${v.sides_done}/${v.sides_total}${q(m)} sides</small></span>
      ${status(v.status)}<span class="num right muted">${v.deaths} deaths</span>
      <span class="num right">${fmtTime(v.ticks)}</span></div>
    ${open ? chaptersBlock(m, ls.chapters) : ""}</section>`;
}

const RANK = { "in progress": 0, completed: 1, "not opened": 2 };

function chaptersBlock(m, list) {
  if (chapters(m).length === 1) return sideTable(list[0]); // a one-chapter mod: straight to its sides
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

function slotBreakdown(perSlot) {
  // "cleared in slots 1, 2; playing in slot 8 (288 deaths)"; more than 6 slots are just counted.
  const groups = new Map();
  for (const [k, v] of perSlot) groups.set(v.status, [...(groups.get(v.status) || []), [k, v]]);
  return [...groups].map(([st, items]) => items.length > 6 ? `${label(st)} in ${items.length} slots`
    : `${label(st)} in slot${items.length > 1 ? "s" : ""} ${items.map(([k]) => k).join(", ")}` +
      (st === "completed" ? "" : ` (${items.map(([, v]) => v.deaths).join(", ")} deaths)`)).join("; ");
}

function sideTable(ch) {
  const sides = countedSides(ch);
  const rows = sides.map((s) => {
    const v = s.progress[state.key];
    const perSlot = Object.entries(s.progress).filter(([k]) => k !== "all");
    const breakdown = state.key === "all" && perSlot.length > 1
      ? `<tr class="slots"><td></td><td colspan="6">${esc(slotBreakdown(perSlot))}</td></tr>` : "";
    return `<tr><td>${chip(s, !!(v && v.heart))}</td>
      <td>${status(sideStatus(s))}</td>
      <td class="right num">${v ? v.deaths : "-"}</td><td class="right num">${v ? fmtTime(v.ticks) : "-"}</td>
      <td class="right num">${v && v.best_ticks ? fmtTime(v.best_ticks) : "-"}</td>
      <td class="right num">${v ? v.berries : "-"}</td><td class="cps">${v ? cps(v.checkpoints) : ""}</td></tr>${breakdown}`;
  }).join("");
  return `<table class="sides"><colgroup><col class="w-side"><col class="w-status"><col class="w-n"><col class="w-n">` +
         `<col class="w-n"><col class="w-n"><col></colgroup><thead><tr><th>Side</th><th>Status</th>` +
         `<th class="right">Deaths</th><th class="right">Time</th><th class="right">Best</th>` +
         `<th class="right">Berries</th><th>Checkpoints reached</th></tr></thead>` +
         `<tbody>${rows || `<tr><td colspan="7" class="muted">Not opened in this slot</td></tr>`}</tbody></table>`;
}

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
  const el = $("sessions");
  const slots = state.data.slots.filter((s) => s.session && (state.key === "all" || s.key === state.key));
  if (!slots.length) { el.hidden = true; return; }
  el.hidden = false;
  const open = sessionsOpen ?? (state.key !== "all" || slots.length <= 3);
  el.innerHTML = `<details${open ? " open" : ""}><summary>Where you left off (Save &amp; Quit): ` +
    `${slots.length} saved session${slots.length > 1 ? "s" : ""}</summary><ul>${slots.map((s) => {
    const x = s.session, m = index.modOfSid[x.sid];
    const chapter = x.title && (!m || x.title !== m.name) ? `${x.title}, ` : (x.title ? "" : `${x.sid}, `);
    return `<li><span class="muted">Slot ${esc(s.key)}:</span> ${m ? `<a data-goto="${esc(m.id)}">${esc(m.name)}</a>, ` : ""}` +
           `${esc(`${chapter}${x.side} side, room ${x.room}`)} <span class="muted">(${x.deaths} deaths this session)</span></li>`;
  }).join("")}</ul></details>`;
}

function renderSummary(rows) {
  const played = state.data.mods.map((m) => viewOf(m)).filter((v) => v.status !== "not started");
  const done = played.filter((v) => COMPLETE.has(v.status)).length;
  const sides = played.reduce((a, v) => [a[0] + v.sides_done, a[1] + v.sides_total], [0, 0]);
  const fig = (label, n, of) => `<span>${label} <b>${fmtNum(n)}</b>${of === undefined ? "" : ` of ${fmtNum(of)}`}</span>`;
  $("summary").innerHTML = fig("Sides cleared", sides[0], sides[1]) + fig("Mods complete", done, played.length) +
    (rows.length !== played.length ? fig("Showing", rows.length) : "");
}

// The header row over the mods (same grid as .mod-head). Click a column name to sort by it.
function listHead() {
  const col = (sort, text, extra = "", title = "") => `<button type="button" data-sort="${sort}" class="${extra}"` +
    `${title ? ` title="${title}"` : ""}${state.sort === sort ? ` aria-sort="${sort === "name" ? "ascending" : "descending"}"` : ""}>${text}</button>`;
  return `<div class="list-head"><span></span>${col("name", "Mod")}${col("progress", "Sides")}<span>Status</span>` +
    `${col("deaths", "Deaths", "right hide-sm")}${col("time", "Time", "right hide-sm")}` +
    `${col("rating", "Slots and tags", "right hide-sm", "Sort by your rating")}</div>`;
}

function render() {
  if (!state.data) return;
  const rows = visibleMods();
  renderSummary(rows);
  renderSessions();
  $("list").innerHTML = rows.length ? listHead() + rows.map(modCard).join("") : `<div class="empty">No mods match.</div>`;
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
  if (sort) { state.sort = sort.dataset.sort; return render(); }
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
  render();
  document.querySelector(`.mod[data-mod="${CSS.escape(a.dataset.goto)}"]`)?.scrollIntoView({ block: "start" });
});

let typingTimer;
$("q").addEventListener("input", (e) => {
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => { state.q = e.target.value; render(); }, 150);
});
$("slot").addEventListener("change", (e) => { state.key = e.target.value; render(); });
$("show").addEventListener("change", (e) => { state.show = e.target.value; render(); });
$("refresh").addEventListener("click", () => load(true));

readHash();
$("q").value = state.q;
$("show").value = state.show;
load();
setInterval(poll, 5000);
