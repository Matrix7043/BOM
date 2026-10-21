"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const SVGNS = "http://www.w3.org/2000/svg";
const state = { datasets: [], ds: null, model: null, mode: "optimize", result: null, selected: null, view: "optimizer" };

// ---------- icons (inline, stroke-based, 24x24) ----------
const ICONS = {
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  chart: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 16v-5M12 16V8M16 16v-3"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  sparkle: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17l.7 1.6 1.6.7-1.6.7L19 21.6l-.7-1.6-1.6-.7 1.6-.7z"/>',
  play: '<path d="M6 4l14 8-14 8z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  alert: '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  arrowUp: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  arrowDown: '<path d="M12 5v14M19 12l-7 7-7-7"/>',
  tv: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M17 2l-5 5-5-5"/>',
  radio: '<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19.1 4.9a10 10 0 0 1 0 14.2M4.9 19.1a10 10 0 0 1 0-14.2"/>',
  newspaper: '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8M15 18h-5M10 6h8v4h-8z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 6l-10 7L2 6"/>',
  video: '<rect x="2" y="5" width="15" height="14" rx="2"/><path d="M22 7l-5 4 5 4z"/>',
  billboard: '<rect x="2" y="3" width="20" height="12" rx="2"/><path d="M8 15v6M16 15v6"/>',
  megaphone: '<path d="M3 11v2a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1z"/><path d="M16 8a5 5 0 0 1 0 8M19 5a9 9 0 0 1 0 14"/>',
};

function icon(name) {
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.megaphone}</svg>`;
}
function hydrateIcons(root = document) {
  $$("[data-icon]", root).forEach((n) => { if (!n.firstChild) n.insertAdjacentHTML("afterbegin", icon(n.dataset.icon)); });
}
function channelIcon(name) {
  const n = name.toLowerCase();
  const rules = [[/tv|television/, "tv"], [/radio|audio|podcast/, "radio"], [/news|print|paper|magazine/, "newspaper"],
    [/search|sem|google|ppc/, "search"], [/social|facebook|meta|insta|tiktok|linkedin/, "users"],
    [/mail|crm|newsletter/, "mail"], [/video|youtube|ctv|ott/, "video"], [/ooh|outdoor|billboard/, "billboard"]];
  return (rules.find(([re]) => re.test(n)) || [, "megaphone"])[1];
}

// ---------- formatting ----------
const color = (i) => (i >= 0 && i < 8 ? `var(--series-${i + 1})` : "var(--series-other)");
const chColor = (name) => color(state.ds.channels.indexOf(name));
const fmt = (v, d = 2) => Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const pval = (p) => (p < 0.001 ? "<0.001" : p.toFixed(3));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function money(v, opts = {}) {
  const unit = state.ds?.spend_unit || "$";
  const d = opts.digits ?? (Math.abs(v) >= 100 ? 1 : 2);
  const num = Number(v).toLocaleString(undefined, { maximumFractionDigits: d });
  return unit.startsWith("$") ? `$${num}${unit.slice(1)}` : `${num} ${unit}`;
}
function moneyParts(v) { // "$" superscript + number + suffix, like the KPI cards
  const unit = state.ds.spend_unit;
  const num = Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
  return unit.startsWith("$") ? `<sup>$</sup>${num}${esc(unit.slice(1))}` : `${num}<sup>${esc(unit)}</sup>`;
}
function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v)), n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}
function pill(node, text, kind) {
  node.className = `pill ${kind}`;
  node.innerHTML = text ? (kind === "up" ? icon("arrowUp") : kind === "down" ? icon("arrowDown") : "") + esc(text) : "";
  $$(".icon", node).forEach((i) => (i.style.cssText = "width:12px;height:12px;stroke-width:2.4"));
}

// ---------- svg + tooltip ----------
function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}
const tip = $("#tooltip");
function showTip(html, evt) {
  tip.innerHTML = html;
  tip.classList.remove("hidden");
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > innerWidth - 8) x = evt.clientX - w - pad;
  if (y + h > innerHeight - 8) y = evt.clientY - h - pad;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
const hideTip = () => tip.classList.add("hidden");
const ttRow = (name, value) =>
  `<div class="tt-row"><span class="dot-sw" style="background:${chColor(name)}"></span>${esc(name)}<b>${value}</b></div>`;

// ---------- api ----------
const rid = () => Math.random().toString(16).slice(2, 14);
async function api(path, opts = {}) {
  const headers = { "X-Request-ID": rid(), ...(opts.headers || {}) };
  const res = await fetch(path, { ...opts, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail
      : Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : res.statusText;
    throw new Error(`${detail} (request ${body.request_id || headers["X-Request-ID"]})`);
  }
  return body;
}
const postJSON = (path, data) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

function setError(sel, msg) {
  const n = $(sel);
  n.textContent = msg || "";
  n.classList.toggle("hidden", !msg);
}
async function withBusy(form, fn) {
  const btn = $("button[type=submit]", form);
  btn.disabled = true;
  try { await fn(); } finally { btn.disabled = false; }
}

// ---------- theme ----------
function currentTheme() {
  return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
}
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  $("#theme-switch").setAttribute("aria-checked", String(t === "dark"));
  try { localStorage.setItem("mmm-theme", t); } catch { /* storage unavailable: theme just won't persist */ }
}
$("#theme-switch").addEventListener("click", () => applyTheme(currentTheme() === "dark" ? "light" : "dark"));

// ---------- navigation ----------
function showView(view) {
  state.view = view;
  $$(".view").forEach((v) => v.classList.toggle("hidden", v.dataset.view !== view));
  $$("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === view));
  closeMenu();
  if (view === "monitoring") refreshMonitoring();
  if (view === "datasets") renderDatasetCards();
  scrollTo({ top: 0 });
}
function routeFromHash() {
  const v = location.hash.slice(1);
  showView(["optimizer", "model", "datasets", "monitoring"].includes(v) ? v : "optimizer");
}
addEventListener("hashchange", routeFromHash);
const closeMenu = () => { $("#sidebar").classList.remove("open"); $("#scrim").classList.remove("open"); };
$("#menu-btn").addEventListener("click", () => { $("#sidebar").classList.toggle("open"); $("#scrim").classList.toggle("open"); });
$("#scrim").addEventListener("click", closeMenu);

// ---------- health ----------
async function pollHealth() {
  const box = $("#status");
  try {
    const h = await fetch("/health").then((r) => r.json());
    box.className = "health ok";
    $("#status-text").textContent = "API healthy";
    $("#version").textContent = `v${h.version} · ${h.env}`;
  } catch {
    box.className = "health down";
    $("#status-text").textContent = "API unreachable";
  }
}

// ---------- datasets ----------
async function loadDatasets(selectId) {
  state.datasets = await api("/api/datasets");
  const sel = $("#dataset");
  sel.innerHTML = state.datasets.map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("");
  sel.value = selectId || state.ds?.id || state.datasets[0].id;
  await selectDataset(sel.value);
}

async function selectDataset(id) {
  state.ds = state.datasets.find((d) => d.id === id);
  state.selected = null;
  $("#dataset").value = id;
  $("#crumb-dataset").textContent = state.ds.name;
  $$("[data-unit]").forEach((n) => (n.textContent = state.ds.spend_unit));
  state.model = await api(`/api/datasets/${encodeURIComponent(id)}/model`);
  renderModelView();
  renderFitCard();
  if (state.view === "datasets") renderDatasetCards();

  $("#budget").value = Math.round(state.ds.typical_total_budget);
  $("#constraints").innerHTML = state.ds.channels.map((c) => `
    <div class="constraint"><span class="label">${esc(c)} <span class="muted">(${esc(state.ds.spend_unit)})</span></span>
      <div class="pair">
        <input type="number" min="0" step="any" data-min="${esc(c)}" placeholder="Min 0" aria-label="${esc(c)} minimum">
        <input type="number" min="0" step="any" data-max="${esc(c)}" placeholder="Max —" aria-label="${esc(c)} maximum">
      </div></div>`).join("");
  $("#split-inputs").innerHTML = state.ds.channels.map((c) => `
    <label class="field">${esc(c)}
      <span class="input-wrap"><span class="prefix">${esc(state.ds.spend_unit)}</span>
      <input type="number" min="0" step="any" data-split="${esc(c)}" value="${Math.round(state.ds.spend_ranges[c].mean)}"></span>
    </label>`).join("");
  await (state.mode === "optimize" ? runOptimize() : runPredict());
}

// ---------- actions ----------
async function runOptimize() {
  setError("#form-error");
  const constraints = {};
  for (const c of state.ds.channels) {
    const min = $(`[data-min="${CSS.escape(c)}"]`).value, max = $(`[data-max="${CSS.escape(c)}"]`).value;
    if (min !== "" || max !== "") constraints[c] = { min: min === "" ? 0 : +min, max: max === "" ? null : +max };
  }
  try {
    const r = await postJSON(`/api/datasets/${encodeURIComponent(state.ds.id)}/optimize`, { budget: +$("#budget").value, constraints });
    render(r);
  } catch (e) { setError("#form-error", e.message); }
}

async function runPredict() {
  setError("#form-error");
  const allocation = {};
  $$("[data-split]").forEach((n) => (allocation[n.dataset.split] = +n.value || 0));
  try {
    render(await postJSON(`/api/datasets/${encodeURIComponent(state.ds.id)}/predict`, { allocation }));
  } catch (e) { setError("#form-error", e.message); }
}

// ---------- optimizer view ----------
function render(r) {
  state.result = r;
  const optimised = !!r.solver;
  $("#alloc-title").textContent = optimised ? "Recommended allocation" : "Your allocation";

  const chip = $("#solver-chip");
  chip.hidden = !optimised;
  if (optimised) chip.innerHTML = `${icon("check")}${esc(r.solver.used)} · ${r.solver.iterations} iterations · ${r.solver.duration_ms} ms`;

  renderSalesCard(r);
  renderBudgetCard(r);
  renderMroiCard(r);
  renderCurves(r);
  renderTiles(r);
  renderAllocTable(r);
  renderShap(r);
  $("#warnings").innerHTML = r.warnings.map((w) => `<div class="callout">${icon("alert")}<span>${esc(w)}</span></div>`).join("");
  $("#justification").innerHTML = r.justification.map((p) => `<li>${esc(p)}</li>`).join("");
}

function renderSalesCard(r) {
  const p = r.prediction, yu = state.ds.sales_unit;
  $("#k-sales").innerHTML = `${fmt(p.mean)}<sup> ${esc(yu)}</sup>`;
  $("#k-sales-label").textContent = `Projected ${state.ds.target} · ${fmt(p.low)} to ${fmt(p.high)}`;
  if (r.optimal_for_same_total !== undefined) {
    const gap = r.optimal_for_same_total - p.mean;
    gap > 0.005 ? pill($("#k-sales-pill"), `${fmt(gap)} vs optimum`, "down") : pill($("#k-sales-pill"), "optimal", "up");
  } else {
    pill($("#k-sales-pill"), `+${fmt(r.lift_total)} lift`, "up");
  }
  // donut
  const host = $("#donut");
  host.innerHTML = "";
  const svg = el("svg", { viewBox: "0 0 100 100", role: "img", "aria-label": "Allocation share by channel" }, host);
  const items = r.channels.filter((c) => c.amount > 1e-9), total = items.reduce((s, c) => s + c.amount, 0);
  el("circle", { cx: 50, cy: 50, r: 40, style: "fill:none;stroke:var(--card-2);stroke-width:10" }, svg);
  const C = 2 * Math.PI * 40;
  let offset = 0;
  for (const c of items) {
    const len = (c.amount / total) * C;
    const arc = el("circle", { cx: 50, cy: 50, r: 40, transform: "rotate(-90 50 50)",
      style: `fill:none;stroke:${chColor(c.name)};stroke-width:10;stroke-dasharray:${Math.max(len - 1.5, 0.5)} ${C};stroke-dashoffset:${-offset}` }, svg);
    arc.addEventListener("mousemove", (e) => showTip(ttRow(c.name, `${money(c.amount)} · ${(c.share * 100).toFixed(1)}%`), e));
    arc.addEventListener("mouseleave", hideTip);
    offset += len;
  }
  $("#donut-legend").innerHTML = r.channels.map((c) => `<li><span class="dot-sw" style="background:${chColor(c.name)}"></span>
    <span class="name">${esc(c.name)}</span><span class="val">${money(c.amount)}</span></li>`).join("");
}

function renderBudgetCard(r) {
  $("#k-budget").innerHTML = moneyParts(r.total);
  const active = r.channels.filter((c) => c.status === "active").length;
  pill($("#k-budget-pill"), `${active}/${r.channels.length} channels`, "neutral");
  const host = $("#mini-bars");
  host.innerHTML = "";
  const n = r.channels.length, W = 240, H = 92, slot = W / n, bw = Math.min(12, slot * 0.4);
  const max = Math.max(...r.channels.map((c) => c.amount), 1e-9);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Spend per channel" }, host);
  r.channels.forEach((c, i) => {
    const x = slot * i + slot / 2 - bw / 2, h = Math.max(2, (c.amount / max) * (H - 22));
    el("rect", { x, y: 2, width: bw, height: H - 22, rx: bw / 2, style: "fill:var(--card-2)" }, svg);
    const bar = el("rect", { x, y: H - 20 - h, width: bw, height: h, rx: bw / 2, style: `fill:${chColor(c.name)}` }, svg);
    const label = el("text", { x: slot * i + slot / 2, y: H - 4, "text-anchor": "middle" }, svg);
    label.textContent = c.name.length > 9 ? `${c.name.slice(0, 8)}…` : c.name;
    for (const node of [bar, label]) {
      node.addEventListener("mousemove", (e) => showTip(ttRow(c.name, money(c.amount)), e));
      node.addEventListener("mouseleave", hideTip);
    }
  });
}

function renderFitCard() {
  const m = state.model, pct = Math.max(0, Math.min(1, m.r_squared));
  $("#k-r2").textContent = m.r_squared.toFixed(3);
  pill($("#k-r2-pill"), `n = ${m.n_obs}`, "neutral");
  $("#k-r2-text").textContent = `Explains ${state.ds.target} variance`;
  $("#k-r2-pct").textContent = `${Math.round(pct * 100)}%`;
  $("#k-r2-bar").style.width = `${pct * 100}%`;
  $("#k-r2-bar").style.background = pct >= 0.7 ? "var(--good)" : pct >= 0.4 ? "var(--warn)" : "var(--bad)";
}

function renderMroiCard(r) {
  const finite = r.channels.filter((c) => c.status === "active" && c.marginal_roi !== null && c.amount > 0);
  const avg = finite.length ? finite.reduce((s, c) => s + c.marginal_roi, 0) / finite.length : null;
  $("#k-mroi").innerHTML = avg === null ? "—" : `${avg.toFixed(4)}<sup> ${esc(state.ds.sales_unit)}</sup>`;
  const unit = money(1, { digits: 0 });
  $("#k-mroi-label").textContent = r.solver
    ? (r.marginal_equalized ? `Per next ${unit}, equalised across channels` : `Avg per next ${unit} (constraints bind)`)
    : `Avg per next ${unit} in this split`;
  $("#avatars").innerHTML = r.channels.map((c) => {
    const on = c.status === "active";
    return `<span class="avatar ${on ? "" : "off"}" style="background:${chColor(c.name)}"
      title="${esc(c.name)}: ${on ? "significant" : c.status} (p ${pval(c.p_value)})">${esc(c.name.slice(0, 2))}</span>`;
  }).join("");
}

function renderCurves(r) {
  const host = $("#curves");
  host.innerHTML = "";
  const W = 620, H = 320, m = { t: 12, r: 16, b: 34, l: 52 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const names = Object.keys(r.curves);
  const xMax = niceMax(Math.max(...names.map((n) => r.curves[n].at(-1)[0])));
  const ys = names.flatMap((n) => r.curves[n].map((p) => p[1]));
  const yMax = niceMax(Math.max(1e-9, ...ys)), yMin = Math.min(0, ...ys);
  const sx = (x) => m.l + (x / xMax) * iw, sy = (y) => m.t + ih - ((y - yMin) / (yMax - yMin)) * ih;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Response curves per channel" }, host);
  const defs = el("defs", {}, svg);
  const grid = el("g", { class: "grid-lines" }, svg);
  for (let i = 0; i <= 5; i++) {
    const yv = yMin + ((yMax - yMin) * i) / 5, xv = (xMax * i) / 5;
    el("line", { x1: m.l, x2: W - m.r, y1: sy(yv), y2: sy(yv) }, grid);
    el("text", { x: m.l - 10, y: sy(yv) + 4, "text-anchor": "end" }, svg).textContent = fmt(yv, yv % 1 ? 1 : 0);
    el("text", { x: sx(xv), y: H - 10, "text-anchor": "middle" }, svg).textContent = money(xv, { digits: 0 });
  }

  names.forEach((n, i) => {
    const g = el("linearGradient", { id: `g${i}`, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0%", style: `stop-color:${chColor(n)};stop-opacity:.28` }, g);
    el("stop", { offset: "100%", style: `stop-color:${chColor(n)};stop-opacity:0` }, g);
  });
  const layers = names.map((n, i) => {
    const pts = r.curves[n].map((p) => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`);
    const area = el("path", { class: "series-area", d: `M${sx(0)},${sy(0)}L${pts.join("L")}L${sx(r.curves[n].at(-1)[0])},${sy(0)}Z`,
      fill: `url(#g${i})` }, svg);
    const line = el("path", { class: "series-line", d: `M${pts.join("L")}`, style: `stroke:${chColor(n)}` }, svg);
    return { n, area, line };
  });
  const dots = r.channels.map((c) => ({ n: c.name, dot: el("circle", { cx: sx(c.amount), cy: sy(c.contribution), r: 5.5,
    style: `fill:${chColor(c.name)};stroke:var(--card);stroke-width:2.5` }, svg) }));

  const applyHighlight = () => {
    for (const { n, area, line } of layers) {
      const dim = state.selected && state.selected !== n;
      area.classList.toggle("dim", dim);
      line.classList.toggle("dim", dim);
      line.style.strokeWidth = state.selected === n ? 3 : 2;
    }
    dots.forEach(({ n, dot }) => dot.classList.toggle("dim", state.selected && state.selected !== n));
  };
  applyHighlight();
  state.applyHighlight = applyHighlight;

  const cross = el("line", { y1: m.t, y2: m.t + ih, style: "stroke:var(--muted);stroke-dasharray:3 3;visibility:hidden" }, svg);
  const hit = el("rect", { x: m.l, y: m.t, width: iw, height: ih, style: "fill:transparent" }, svg);
  hit.addEventListener("mousemove", (e) => {
    const box = svg.getBoundingClientRect();
    const xv = Math.max(0, Math.min(xMax, ((((e.clientX - box.left) / box.width) * W - m.l) / iw) * xMax));
    cross.setAttribute("x1", sx(xv));
    cross.setAttribute("x2", sx(xv));
    cross.style.visibility = "visible";
    const f = state.model.transform === "sqrt" ? Math.sqrt : Math.log1p;
    showTip(`<div><b>Spend ${money(xv)}</b></div>` + r.channels.map((c) => ttRow(c.name, fmt(c.coef * f(xv)))).join(""), e);
  });
  hit.addEventListener("mouseleave", () => { cross.style.visibility = "hidden"; hideTip(); });

  $("#curves-legend").innerHTML = names.map((n) =>
    `<span><span class="dot-sw" style="background:${chColor(n)}"></span>${esc(n)}</span>`).join("");
}

function renderTiles(r) {
  $("#tiles").innerHTML = r.channels.map((c) => `
    <button class="tile" role="tab" data-ch="${esc(c.name)}" aria-selected="${state.selected === c.name}">
      ${icon(channelIcon(c.name))}<span>${esc(c.name)}</span><span class="tile-val">${(c.share * 100).toFixed(0)}%</span>
    </button>`).join("");
  $$(".tile").forEach((t) => t.addEventListener("click", () => {
    state.selected = state.selected === t.dataset.ch ? null : t.dataset.ch;
    $$(".tile").forEach((n) => n.setAttribute("aria-selected", String(n.dataset.ch === state.selected)));
    $$("#alloc-table tbody tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.ch === state.selected));
    state.applyHighlight?.();
  }));
}

function statusBadge(status) {
  return status === "active"
    ? `<span class="status active">${icon("check")}Significant</span>`
    : `<span class="status ${status}">${icon("x")}${status === "negative" ? "Negative" : "Not significant"}</span>`;
}

function renderAllocTable(r) {
  const rows = r.channels.map((c) => {
    const roi = c.status !== "active" ? "—" : c.marginal_roi === null ? "∞" : c.marginal_roi.toFixed(4);
    const flag = c.extrapolated ? `<span class="warn-flag" title="Above the training range (max ${money(c.train_max)})">${icon("alert")}</span>` : "";
    return `<tr data-ch="${esc(c.name)}" class="${state.selected === c.name ? "selected" : ""}">
      <td><div class="ch-cell"><span class="ch-icon" style="--sw:${chColor(c.name)}">${icon(channelIcon(c.name))}</span>
        <div><div class="ch-name">${esc(c.name)}${flag}</div><div class="ch-meta">β ${c.coef.toFixed(3)} · p ${pval(c.p_value)}</div></div></div></td>
      <td class="num">${money(c.amount)}</td>
      <td class="num">${(c.share * 100).toFixed(1)}%</td>
      <td class="num">${fmt(c.contribution)}</td>
      <td class="num">${roi}</td>
      <td>${statusBadge(c.status)}</td></tr>`;
  }).join("");
  $("#alloc-table").innerHTML = `<thead><tr><th>Channel</th><th class="num">Spend</th><th class="num">Share</th>
    <th class="num">Lift</th><th class="num">Marginal ROI</th><th>Status</th></tr></thead><tbody>${rows}</tbody>`;
}

function renderShap(r) {
  const host = $("#shap");
  host.innerHTML = "";
  $("#shap-sub").textContent = `Contribution vs the average training prediction (${fmt(r.shap_base_value)} ${state.ds.sales_unit})`;
  const rowH = 44, W = 620, m = { t: 6, r: 64, b: 30, l: 100 };
  const H = m.t + m.b + rowH * r.channels.length, iw = W - m.l - m.r;
  const maxAbs = niceMax(Math.max(1e-9, ...r.channels.map((c) => Math.abs(c.shap))));
  const sx = (v) => m.l + ((v + maxAbs) / (2 * maxAbs)) * iw;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "SHAP values per channel" }, host);
  const grid = el("g", { class: "grid-lines" }, svg);
  for (const v of [-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs]) {
    el("line", { x1: sx(v), x2: sx(v), y1: m.t, y2: H - m.b }, grid);
    el("text", { x: sx(v), y: H - 8, "text-anchor": "middle" }, svg).textContent = (v > 0 ? "+" : "") + fmt(v, 1);
  }
  el("line", { x1: sx(0), x2: sx(0), y1: m.t, y2: H - m.b, style: "stroke:var(--muted)" }, svg);
  r.channels.forEach((c, i) => {
    const y = m.t + i * rowH + 11, h = rowH - 22;
    const x0 = Math.min(sx(0), sx(c.shap)), w = Math.max(2, Math.abs(sx(c.shap) - sx(0)));
    el("text", { x: m.l - 14, y: y + h / 2 + 4, "text-anchor": "end", style: "fill:var(--text);font-size:12px" }, svg).textContent = c.name;
    el("rect", { x: m.l, y: y - 4, width: iw, height: h + 8, rx: 6, style: "fill:var(--card-2);opacity:.5" }, svg);
    const bar = el("rect", { x: x0, y, width: w, height: h, rx: 5, style: `fill:${chColor(c.name)}` }, svg);
    el("text", { x: c.shap >= 0 ? x0 + w + 8 : x0 - 8, y: y + h / 2 + 4, "text-anchor": c.shap >= 0 ? "start" : "end",
      style: "fill:var(--text);font-weight:600" }, svg).textContent = (c.shap >= 0 ? "+" : "") + fmt(c.shap);
    bar.addEventListener("mousemove", (e) => showTip(`${ttRow(c.name, (c.shap >= 0 ? "+" : "") + fmt(c.shap))}
      <div class="tt-row muted">Lift above intercept<b>${fmt(c.contribution)}</b></div>`, e));
    bar.addEventListener("mouseleave", hideTip);
  });
  const top = [...r.channels].sort((a, b) => b.contribution - a.contribution)[0];
  $("#shap-note").textContent = r.lift_total > 0 && top
    ? `${top.name} drives ${(top.lift_share * 100).toFixed(0)}% of the ${fmt(r.lift_total)} ${state.ds.sales_unit} lift above the zero-spend baseline.`
    : "";
}

// ---------- model view ----------
function statCard(label, value, foot) {
  return `<article class="card stat"><p class="kpi-label">${esc(label)}</p><span class="kpi-value">${value}</span>
    <p class="stat-foot">${foot}</p></article>`;
}
function renderModelView() {
  const m = state.model;
  $("#model-stats").innerHTML = [
    statCard("R²", m.r_squared.toFixed(3), `adjusted ${m.adj_r_squared.toFixed(3)}`),
    statCard("Observations", m.n_obs, `F-test p ${pval(m.f_p_value)}`),
    statCard("Residual SD", m.residual_sd.toFixed(3), esc(state.ds.sales_unit)),
    statCard("Intercept", m.intercept.toFixed(3), `p ${pval(m.intercept_p_value)} · condition # ${Math.round(m.condition_number)}`),
  ].join("");
  $("#model-eq").innerHTML = `<code class="eq">${esc(m.equation)}</code> · α = ${m.alpha} · SHAP via ${esc(m.shap_backend)}`;
  $("#coef-table").innerHTML = `<thead><tr><th>Channel</th><th class="num">Coef</th><th class="num">Std err</th><th class="num">p-value</th>
    <th class="num">${Math.round((1 - m.alpha) * 100)}% CI</th><th class="num">Training range</th><th>Status</th></tr></thead><tbody>` +
    m.channels.map((c) => `<tr>
      <td><div class="ch-cell"><span class="ch-icon" style="--sw:${chColor(c.name)}">${icon(channelIcon(c.name))}</span><span class="ch-name">${esc(c.name)}</span></div></td>
      <td class="num">${c.coef.toFixed(4)}</td><td class="num">${c.std_err.toFixed(4)}</td><td class="num">${pval(c.p_value)}</td>
      <td class="num">[${c.ci_low.toFixed(3)}, ${c.ci_high.toFixed(3)}]</td>
      <td class="num">${money(c.train_min)} – ${money(c.train_max)}</td><td>${statusBadge(c.status)}</td></tr>`).join("") + "</tbody>";
  const gt = state.ds.ground_truth;
  $("#truth-note").textContent = gt
    ? `Ground truth used to generate this data: intercept ${gt.intercept}, ` +
      Object.entries(gt.coefficients).map(([k, v]) => `${k} ${v}`).join(", ") + ". The CIs above should contain these values."
    : "";
}

// ---------- datasets view ----------
function renderDatasetCards() {
  $("#dataset-cards").innerHTML = state.datasets.map((d) => `
    <article class="card ds-card ${d.id === state.ds?.id ? "current" : ""}">
      <div class="ds-top"><h2>${esc(d.name)}</h2>
        <span class="pill ${d.source === "builtin" ? "neutral" : "up"}">${d.source === "builtin" ? "Built-in" : "Uploaded"}</span></div>
      <p class="ds-desc">${esc(d.description)}</p>
      <div class="ds-chips">${d.channels.map((c) => `<span>${esc(c)}</span>`).join("")}</div>
      <div class="ds-foot"><span>${d.rows} rows · target ${esc(d.target)} · ${esc(d.spend_unit)}</span>
        ${d.id === state.ds?.id ? '<span class="pill up">In use</span>'
          : `<button class="ghost-btn" data-use="${esc(d.id)}">Use dataset</button>`}</div>
    </article>`).join("");
  $$("[data-use]").forEach((b) => b.addEventListener("click", async () => {
    await selectDataset(b.dataset.use);
    location.hash = "optimizer";
  }));
}

function parseHeader(line) {
  const out = [];
  let cur = "", quoted = false;
  for (const ch of line) {
    if (ch === '"') quoted = !quoted;
    else if (ch === "," && !quoted) { out.push(cur.trim()); cur = ""; }
    else cur += ch;
  }
  out.push(cur.trim());
  return out.filter(Boolean);
}

async function onFileChosen(f) {
  setError("#upload-error");
  if (!f) return;
  $("#file-label").innerHTML = `<b>${esc(f.name)}</b> · ${(f.size / 1024).toFixed(1)} KB`;
  const head = (await f.slice(0, 64 * 1024).text()).split(/\r?\n/)[0].replace(/^﻿/, "");
  const cols = parseHeader(head);
  const guess = cols.find((c) => /sales|revenue|conversions|target|kpi/i.test(c)) || cols.at(-1);
  $("#target").innerHTML = cols.map((c) => `<option ${c === guess ? "selected" : ""}>${esc(c)}</option>`).join("");
  $("#channel-picks").innerHTML = cols.map((c) => `<label><input type="checkbox" value="${esc(c)}"
    ${c !== guess && !/^(unnamed|date|week|id|index)/i.test(c) ? "checked" : ""}>${esc(c)}</label>`).join("");
  $("#ds-name").value = f.name.replace(/\.csv$/i, "");
  $("#column-pickers").classList.remove("hidden");
}
$("#file").addEventListener("change", (e) => onFileChosen(e.target.files[0]));
const dz = $("#dropzone");
["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((t) => dz.addEventListener(t, () => dz.classList.remove("drag")));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  if (!e.dataTransfer.files.length) return;
  $("#file").files = e.dataTransfer.files;
  onFileChosen(e.dataTransfer.files[0]);
});

$("#upload-form").addEventListener("submit", (e) => {
  e.preventDefault();
  withBusy(e.target, async () => {
    setError("#upload-error");
    const fd = new FormData();
    fd.append("file", $("#file").files[0]);
    fd.append("name", $("#ds-name").value);
    fd.append("target", $("#target").value);
    fd.append("channels", $$("#channel-picks input:checked").map((n) => n.value).join(","));
    fd.append("spend_unit", $("#spend-unit").value);
    fd.append("sales_unit", $("#sales-unit").value);
    try {
      const r = await api("/api/datasets", { method: "POST", body: fd });
      await loadDatasets(r.dataset.id);
      location.hash = "optimizer";
    } catch (err) { setError("#upload-error", err.message); }
  });
});

// ---------- monitoring view ----------
function parseProm(text) {
  const out = [];
  for (const line of text.split("\n")) {
    const m = line.match(/^([a-zA-Z_:][\w:]*)(?:\{([^}]*)\})?\s+(\S+)/);
    if (!m) continue;
    const labels = {};
    for (const [, k, v] of (m[2] || "").matchAll(/(\w+)="([^"]*)"/g)) labels[k] = v;
    out.push({ name: m[1], labels, value: parseFloat(m[3]) });
  }
  return out;
}
const sumOf = (rows, name, pred = () => true) => rows.filter((r) => r.name === name && pred(r.labels)).reduce((s, r) => s + r.value, 0);

async function refreshMonitoring() {
  if (state.view !== "monitoring") return;
  try {
    const [health, ready, text] = await Promise.all([
      fetch("/health").then((r) => r.json()),
      fetch("/ready").then((r) => r.json()),
      fetch("/metrics").then((r) => r.text()),
    ]);
    const rows = parseProm(text);
    const total = sumOf(rows, "mmm_http_requests_total");
    const errors = sumOf(rows, "mmm_http_requests_total", (l) => l.status?.startsWith("5"));
    const optOk = sumOf(rows, "mmm_optimizations_total", (l) => l.status === "ok");
    const optBad = sumOf(rows, "mmm_optimizations_total", (l) => l.status !== "ok");
    const optSum = sumOf(rows, "mmm_optimizer_duration_seconds_sum"), optCnt = sumOf(rows, "mmm_optimizer_duration_seconds_count");
    const uptime = health.uptime_s, upTxt = uptime > 3600 ? `${(uptime / 3600).toFixed(1)} h` : uptime > 60 ? `${Math.round(uptime / 60)} min` : `${Math.round(uptime)} s`;

    $("#mon-stats").innerHTML = [
      statCard("Service", `<span class="pill ${ready.ready ? "up" : "down"}">${ready.ready ? "Ready" : "Not ready"}</span>`,
        `v${esc(health.version)} · ${esc(health.env)} · up ${upTxt}`),
      statCard("HTTP requests", total.toLocaleString(), `${errors} server errors (${total ? ((errors / total) * 100).toFixed(2) : 0}%)`),
      statCard("Optimisations", optOk.toLocaleString(), `${optBad} rejected or failed`),
      statCard("Avg solve time", optCnt ? `${((optSum / optCnt) * 1000).toFixed(1)} ms` : "—", `${optCnt} SLSQP runs`),
    ].join("");

    const routes = {};
    const route = (k) => (routes[k] ??= { count: 0, errors: 0, sum: 0, n: 0 });
    for (const r of rows) {
      if (r.name === "mmm_http_requests_total") {
        route(r.labels.route).count += r.value;
        if (/^[45]/.test(r.labels.status)) route(r.labels.route).errors += r.value;
      }
      if (r.name === "mmm_http_request_duration_seconds_sum") route(r.labels.route).sum = r.value;
      if (r.name === "mmm_http_request_duration_seconds_count") route(r.labels.route).n = r.value;
    }
    $("#mon-routes").innerHTML = `<thead><tr><th>Route</th><th class="num">Requests</th><th class="num">4xx/5xx</th><th class="num">Avg latency</th></tr></thead><tbody>` +
      Object.entries(routes).sort((a, b) => b[1].count - a[1].count).map(([k, v]) => `<tr><td><code class="eq">${esc(k)}</code></td>
        <td class="num">${v.count}</td><td class="num">${v.errors}</td><td class="num">${v.n ? ((v.sum / v.n) * 1000).toFixed(1) + " ms" : "—"}</td></tr>`).join("") + "</tbody>";

    const val = (name, id) => rows.find((r) => r.name === name && r.labels.dataset === id)?.value;
    $("#mon-models").innerHTML = `<thead><tr><th>Dataset</th><th class="num">R²</th><th class="num">Runs</th><th class="num">Gap to exact</th><th class="num">Extrapolations</th></tr></thead><tbody>` +
      state.datasets.map(({ id }) => {
        const r2 = val("mmm_model_r_squared", id), gap = val("mmm_optimizer_analytic_gap_ratio", id);
        const ex = sumOf(rows, "mmm_extrapolation_warnings_total", (l) => l.dataset === id);
        const runs = sumOf(rows, "mmm_optimizations_total", (l) => l.dataset === id);
        return `<tr><td class="ch-name">${esc(id)}</td><td class="num">${r2 === undefined ? "—" : r2.toFixed(3)}</td><td class="num">${runs}</td>
          <td class="num">${gap === undefined ? "—" : gap.toExponential(1)}</td><td class="num">${ex}</td></tr>`;
      }).join("") + "</tbody>";
  } catch {
    $("#mon-stats").innerHTML = statCard("Service", '<span class="pill down">Unreachable</span>', "Could not reach the API");
  }
}

// ---------- wiring ----------
$$(".seg").forEach((b) => b.addEventListener("click", () => {
  state.mode = b.dataset.mode;
  $$(".seg").forEach((n) => { n.classList.toggle("active", n === b); n.setAttribute("aria-selected", String(n === b)); });
  $$(".mode-form").forEach((f) => f.classList.toggle("hidden", f.dataset.mode !== state.mode));
  setError("#form-error");
}));
$("#toggle-constraints").addEventListener("click", (e) => {
  const open = !$("#constraints").classList.toggle("hidden");
  e.currentTarget.setAttribute("aria-expanded", String(open));
});
$("#dataset").addEventListener("change", (e) => selectDataset(e.target.value).catch((err) => setError("#form-error", err.message)));
$("#optimize-form").addEventListener("submit", (e) => { e.preventDefault(); withBusy(e.target, runOptimize); });
$("#predict-form").addEventListener("submit", (e) => { e.preventDefault(); withBusy(e.target, runPredict); });

hydrateIcons();
applyTheme(currentTheme());
routeFromHash();
pollHealth();
setInterval(pollHealth, 15000);
setInterval(refreshMonitoring, 10000);
loadDatasets().catch((e) => setError("#form-error", e.message));
