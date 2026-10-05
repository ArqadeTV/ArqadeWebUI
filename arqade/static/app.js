(() => {
"use strict";

/* ---------- tiny helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el) { try { el[k] = v; } catch { el.setAttribute(k, v); } }
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const ICONS = {
  cube: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5M3 17.5l9 5 9-5" opacity=".6"/>',
  box: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h0a1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
};
const icon = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;
const paintIcons = (root = document) => $$("i[data-i]", root).forEach((i) => { i.innerHTML = icon(i.dataset.i); });

async function api(path, opts = {}) {
  const o = { headers: {}, ...opts };
  if (o.body && typeof o.body !== "string") { o.body = JSON.stringify(o.body); o.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch { /* non-JSON */ }
  if (!r.ok) {
    let d = data && data.detail;
    if (Array.isArray(d)) d = d.map((x) => x.msg).join("; ");
    throw new Error(d || r.statusText || "Request failed");
  }
  return data;
}
function toast(msg, kind = "") {
  const t = h("div", { class: "toast " + kind, text: msg });
  $("#toasts").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
}
const fmtBytes = (n) => {
  if (!n && n !== 0) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n >= 100 || i === 0 ? n.toFixed(0) : n.toFixed(1)} ${u[i]}`;
};
const fmtNum = (n) => (n >= 1e9 ? (n / 1e9).toFixed(2) + " B" : n >= 1e6 ? (n / 1e6).toFixed(1) + " M" : n >= 1e3 ? (n / 1e3).toFixed(1) + " K" : String(n));
const fmtDate = (t) => (t ? new Date(t * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "");
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied", "ok"); }
  catch { const ta = h("textarea", { value: text }); document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove(); toast("Copied", "ok"); }
}
function drawer(title, ...content) {
  $("#drTitle").textContent = title;
  const body = $("#drBody"); body.textContent = ""; body.append(...content.flat().filter(Boolean));
  $("#drawer").hidden = false;
}
$("#drClose").onclick = () => { $("#drawer").hidden = true; };
$("#drawer").addEventListener("click", (e) => { if (e.target.id === "drawer") $("#drawer").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").hidden = true; });
function kvTable(obj) {
  const t = h("table", { class: "kv" });
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === "") continue;
    t.append(h("tr", {}, h("td", { text: k }), h("td", { text: typeof v === "object" ? JSON.stringify(v, null, 1) : String(v) })));
  }
  return t;
}

/* ---------- theme wiring ---------- */
const T = window.ArqadeTheme;
T.onChange((s) => {
  $("#themeBtn").innerHTML = icon(s.effective === "dark" ? "moon" : "sun");
  const chip = $("#extChip");
  chip.hidden = !s.autoLight;
  chip.textContent = s.autoLight ? `${s.detected} detected → light base` : "";
  const sel = $("#setTheme"), g = $("#setGuard"), st = $("#extStatus");
  if (sel) { sel.value = s.pref; g.checked = s.guard; }
  if (st) st.textContent = s.detected
    ? `Detected: ${s.detected}. ${s.autoLight ? "Arqade is using its light theme so the extension can darken it cleanly." : "Auto-switch is off or overridden, so your chosen theme is used."}`
    : "No dark-mode extension detected right now. (Browser-level 'force dark' flags can't be detected, but Arqade declares dark+light support so they leave it alone.)";
});
$("#themeBtn").onclick = () => T.toggle();
$("#setTheme").onchange = (e) => T.setPref(e.target.value);
$("#setGuard").onchange = (e) => T.setGuard(e.target.checked);

/* ---------- router ---------- */
const VIEWS = { models: "Models", chat: "Chat", prompts: "Prompts & Hierarchy", libraries: "Libraries", system: "System", settings: "Settings" };
const inited = {};
const onShow = { chat: () => initChat(), prompts: () => initPrompts(), libraries: () => loadLibs(), system: () => loadSystem(), settings: () => loadSettings() };
function route() {
  let v = location.hash.slice(1);
  if (!VIEWS[v]) v = "models";
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === v));
  $("#title").textContent = VIEWS[v];
  $("#side").classList.remove("open");
  if (onShow[v]) onShow[v]();
  inited[v] = true;
}
window.addEventListener("hashchange", route);
$("#menuBtn").onclick = () => $("#side").classList.toggle("open");

/* ---------- models & scanning ---------- */
const M = { all: [], fmt: null, q: "", sort: "size", limit: 200 };
const chatTarget = (m) => {
  if (m.format === "Ollama") return { kind: "ollama", model: m.ollama_name };
  if (m.format === "GGUF") return { kind: "llama_cpp", model_id: m.id };
  if (m.format === "HF Transformers") return { kind: "transformers", model_id: m.id };
  return null;
};

async function loadModels() {
  M.all = (await api("/api/models")).models;
  renderModels();
}
function renderModels() {
  const all = M.all;
  const total = all.reduce((a, m) => a + m.size, 0);
  const byFmt = {};
  all.forEach((m) => { byFmt[m.format] = (byFmt[m.format] || 0) + 1; });
  const stat = (b, s) => h("div", { class: "stat" }, h("b", { text: b }), h("span", { text: s }));
  $("#stats").replaceChildren(
    stat(all.length, "models found"), stat(fmtBytes(total), "total size"),
    stat(Object.keys(byFmt).length, "formats"), stat(all.filter((m) => m.unsafe_pickle).length, "pickle-based (trust check)")
  );
  const chips = [h("button", { class: M.fmt ? "" : "on", text: `All ${all.length}`, onclick: () => { M.fmt = null; renderModels(); } })];
  Object.entries(byFmt).sort((a, b) => b[1] - a[1]).forEach(([f, c]) =>
    chips.push(h("button", { class: M.fmt === f ? "on" : "", text: `${f} ${c}`, onclick: () => { M.fmt = f; renderModels(); } })));
  $("#fmtChips").replaceChildren(...chips);

  const q = M.q.toLowerCase();
  let rows = all.filter((m) => (!M.fmt || m.format === M.fmt) && (!q || (m.name + " " + m.path + " " + m.source).toLowerCase().includes(q)));
  rows.sort((a, b) => (M.sort === "name" ? a.name.localeCompare(b.name) : M.sort === "mtime" ? b.mtime - a.mtime : b.size - a.size));
  const list = $("#modelList");
  if (!rows.length) {
    list.replaceChildren(h("div", { class: "empty", text: all.length ? "No models match your filters." : "No models yet — press Scan to look for them. 🔍" }));
    return;
  }
  const shown = rows.slice(0, M.limit);
  list.replaceChildren(...shown.map(modelRow));
  if (rows.length > shown.length) list.append(h("button", { class: "btn", text: `Show ${Math.min(200, rows.length - shown.length)} more (${rows.length - shown.length} hidden)`, onclick: () => { M.limit += 200; renderModels(); } }));
}
function modelRow(m) {
  const tags = h("div", { class: "tags" },
    h("span", { class: "chip accent", text: m.format }), h("span", { class: "chip", text: m.framework }),
    h("span", { class: "chip", text: m.source }), h("span", { class: "chip", text: fmtBytes(m.size) }),
    m.shards ? h("span", { class: "chip", text: `${m.shards} shards` }) : null,
    m.unsafe_pickle ? h("span", { class: "chip warn", title: "Pickle files can execute code when loaded. Arqade never loads them.", text: "pickle" }) : null,
    h("span", { class: "chip", text: fmtDate(m.mtime) }));
  const target = chatTarget(m);
  return h("div", { class: "model" },
    h("div", { class: "nm", title: m.name, text: m.name }),
    h("div", { class: "acts" },
      h("button", { class: "btn sm", text: "Inspect", onclick: () => inspectModel(m) }),
      target ? h("button", { class: "btn sm primary", text: "Chat", onclick: () => { Chat.pending = target; location.hash = "#chat"; if (inited.chat) applyPending(); } }) : null,
      h("button", { class: "btn sm", text: "Reveal", onclick: () => api(`/api/models/${m.id}/reveal`, { method: "POST" }).catch((e) => toast(e.message, "err")) }),
      h("button", { class: "btn sm", text: "Copy path", onclick: () => copy(m.path) })),
    h("div", { class: "path", title: m.path, text: m.path }), tags);
}
async function inspectModel(m) {
  drawer(m.name, h("p", { class: "muted", text: "Reading metadata…" }));
  try {
    const d = await api(`/api/models/${m.id}/inspect`);
    const det = { ...d.details };
    if (det.parameters) det["parameters (human)"] = fmtNum(det.parameters);
    drawer(m.name,
      h("h3", { text: "File" }), kvTable({ Path: m.path, Format: m.format, Framework: m.framework, Size: fmtBytes(m.size), Source: m.source, Modified: fmtDate(m.mtime) }),
      m.unsafe_pickle ? h("p", { class: "chip warn", text: "Pickle-based format — only load files you trust. Arqade only lists them." }) : null,
      h("h3", { text: "Metadata" }), Object.keys(det).length ? kvTable(det) : h("p", { class: "muted", text: "No extra metadata for this format." }));
  } catch (e) { drawer(m.name, h("p", { class: "chip bad", text: e.message })); }
}
$("#modelSearch").oninput = debounce((e) => { M.q = e.target.value; M.limit = 200; renderModels(); }, 120);
$("#modelSort").onchange = (e) => { M.sort = e.target.value; renderModels(); };

let scanTimer = null;
function paintScan(s) {
  $("#scanBtn").disabled = s.running;
  $("#scanCancel").hidden = !s.running;
  $("#scanProg").hidden = !s.running;
  $("#scanLine").textContent = s.running
    ? `${s.dirs.toLocaleString()} folders · ${s.files.toLocaleString()} files · ${s.found} models — ${s.current}`
    : s.finished ? `Last scan: ${s.found} models in ${s.elapsed.toFixed(1)}s${s.error ? " — " + s.error : ""}` : "";
}
async function pollScan(announce) {
  clearTimeout(scanTimer);
  let s;
  try { s = await api("/api/scan"); } catch (e) { return toast(e.message, "err"); }
  paintScan(s);
  await loadModels().catch(() => {});
  if (s.running) scanTimer = setTimeout(() => pollScan(true), 900);
  else if (announce) toast(`Scan finished — ${s.found} models`, "ok");
}
$("#scanBtn").onclick = async () => {
  try {
    const mode = $("#scanMode").value;
    if (mode === "deep" && !confirm("Deep scan walks every drive and can take a while. Continue?")) return;
    await api("/api/scan", { method: "POST", body: { mode } });
    pollScan(true);
  } catch (e) { toast(e.message, "err"); }
};
$("#scanCancel").onclick = () => api("/api/scan/cancel", { method: "POST" });

/* ---------- prompt hierarchy state (shared by Chat + Prompts) ---------- */
const P = { h: null, presets: { builtin: {}, saved: {} }, def: null };
const clone = (o) => JSON.parse(JSON.stringify(o));
function saveHier() { try { localStorage.setItem("arqade.hierarchy", JSON.stringify(P.h)); } catch { /* ignore */ } }
async function loadPresets() {
  const d = await api("/api/prompts");
  P.presets = { builtin: d.builtin, saved: d.saved }; P.def = d.default;
  if (!P.h) {
    try { P.h = JSON.parse(localStorage.getItem("arqade.hierarchy") || "null"); } catch { P.h = null; }
    if (!P.h || !Array.isArray(P.h.layers)) P.h = clone(d.default);
  }
}
function fillPresetSelect(sel, withCurrent) {
  const opts = [];
  if (withCurrent) opts.push(h("option", { value: "", text: "— current (edited) —" }));
  const group = (label, obj, prefix) => {
    const names = Object.keys(obj);
    if (names.length) opts.push(h("optgroup", { label }, names.map((n) => h("option", { value: prefix + n, text: n }))));
  };
  group("Built-in", P.presets.builtin, "b:"); group("Saved", P.presets.saved, "s:");
  sel.replaceChildren(...opts);
}
function presetByValue(v) {
  const [kind, ...rest] = v.split(":"); const name = rest.join(":");
  return clone((kind === "b" ? P.presets.builtin : P.presets.saved)[name] || P.def);
}

/* ---------- prompts view ---------- */
let promptsReady = false;
async function initPrompts() {
  if (!promptsReady) {
    try { await loadPresets(); } catch (e) { return toast(e.message, "err"); }
    promptsReady = true;
    bindPromptUI();
  }
  fillPresetSelect($("#prPreset"), false);
  renderPrompts();
}
function bindPromptUI() {
  $("#modeSeg").addEventListener("click", (e) => { const m = e.target.dataset.mode; if (m) { P.h.mode = m; saveHier(); renderPrompts(); } });
  $("#policy").onchange = (e) => { P.h.conflict_policy = e.target.value; edited(); };
  $("#simpleText").oninput = (e) => { P.h.simple_text = e.target.value; edited(); };
  $("#addLayer").onclick = () => {
    if (P.h.layers.length >= 12) return toast("Max 12 layers", "err");
    P.h.layers.push({ id: Math.random().toString(36).slice(2, 10), name: "New layer", text: "", enabled: true, locked: false, untrusted: false });
    edited(); renderPrompts();
  };
  $("#prLoad").onclick = () => { const v = $("#prPreset").value; if (!v) return; P.h = presetByValue(v); saveHier(); renderPrompts(); toast("Preset loaded", "ok"); };
  $("#prSave").onclick = async () => {
    const name = $("#prName").value.trim();
    if (!name) return toast("Type a preset name first", "err");
    try { await api("/api/prompts", { method: "POST", body: { name, hierarchy: P.h } }); await loadPresets(); fillPresetSelect($("#prPreset"), false); $("#prPreset").value = "s:" + name; toast("Saved", "ok"); }
    catch (e) { toast(e.message, "err"); }
  };
  $("#prDel").onclick = async () => {
    const v = $("#prPreset").value;
    if (!v.startsWith("s:")) return toast("Only saved presets can be deleted", "err");
    if (!confirm(`Delete preset "${v.slice(2)}"?`)) return;
    try { await api("/api/prompts/" + encodeURIComponent(v.slice(2)), { method: "DELETE" }); await loadPresets(); fillPresetSelect($("#prPreset"), false); toast("Deleted", "ok"); }
    catch (e) { toast(e.message, "err"); }
  };
}
const edited = () => { saveHier(); refreshPreview(); };
const refreshPreview = debounce(async () => {
  try {
    const d = await api("/api/prompts/compile", { method: "POST", body: { hierarchy: P.h } });
    $("#compiled").textContent = d.system || "(empty — the model gets no system prompt)";
    $("#tokEst").textContent = `~${d.tokens} tokens`;
  } catch (e) { $("#compiled").textContent = e.message; }
}, 200);
function renderPrompts() {
  const simple = P.h.mode === "simple";
  $$("#modeSeg button").forEach((b) => b.classList.toggle("on", b.dataset.mode === P.h.mode));
  $("#simpleBox").hidden = !simple; $("#hierBox").hidden = simple;
  $("#simpleText").value = P.h.simple_text || ""; $("#policy").value = P.h.conflict_policy;
  const box = $("#layers"); box.textContent = "";
  let rank = 0;
  P.h.layers.forEach((l, i) => {
    if (l.enabled && !l.untrusted) rank++;
    const mv = (d) => { const j = i + d; if (j < 0 || j >= P.h.layers.length) return; [P.h.layers[i], P.h.layers[j]] = [P.h.layers[j], P.h.layers[i]]; edited(); renderPrompts(); };
    const flag = (key, label, tip) => h("label", { title: tip }, h("input", { type: "checkbox", checked: l[key], onchange: (e) => { l[key] = e.target.checked; edited(); renderPrompts(); } }), label);
    box.append(h("div", { class: "layer" + (l.untrusted ? " untrusted" : "") + (l.enabled ? "" : " off") },
      h("div", { class: "head" },
        h("span", { class: "prio", text: !l.enabled ? "OFF" : l.untrusted ? "DATA" : "P" + rank }),
        h("input", { value: l.name, maxLength: 80, "aria-label": "Layer name", oninput: (e) => { l.name = e.target.value; edited(); } }),
        h("button", { class: "icon-btn", style: "width:30px;height:30px", title: "Higher authority", text: "↑", onclick: () => mv(-1) }),
        h("button", { class: "icon-btn", style: "width:30px;height:30px", title: "Lower authority", text: "↓", onclick: () => mv(1) }),
        h("button", { class: "icon-btn", style: "width:30px;height:30px", title: "Delete layer", text: "✕", onclick: () => { P.h.layers.splice(i, 1); edited(); renderPrompts(); } })),
      h("textarea", { rows: 3, value: l.text, placeholder: "Instructions for this layer…", oninput: (e) => { l.text = e.target.value; edited(); } }),
      h("div", { class: "flags" },
        flag("enabled", "Enabled", "Skip this layer when off"),
        flag("locked", "Locked", "Declared immutable: lower layers cannot modify or relax it"),
        flag("untrusted", "Untrusted data", "Treated as data, never obeyed"))));
  });
  refreshPreview();
}

/* ---------- chat ---------- */
const Chat = { backends: [], messages: [], ctrl: null, pending: null };
let chatReady = false;
async function initChat() {
  if (!chatReady) {
    chatReady = true;
    try { await loadPresets(); } catch (e) { toast(e.message, "err"); }
    fillPresetSelect($("#chPreset"), true);
    $("#chPreset").onchange = (e) => { if (!e.target.value) return; P.h = presetByValue(e.target.value); saveHier(); promptsReady && renderPrompts(); toast("Prompt preset applied", "ok"); e.target.value = ""; };
    $("#chBackend").onchange = fillModels;
    $("#chTemp").oninput = (e) => { $("#tVal").textContent = e.target.value; };
    $("#chTopP").oninput = (e) => { $("#pVal").textContent = e.target.value; };
    $("#chSend").onclick = sendChat;
    $("#chStop").onclick = () => Chat.ctrl && Chat.ctrl.abort();
    $("#chClear").onclick = () => { Chat.messages = []; $("#msgs").replaceChildren(h("div", { class: "empty", text: "Cleared. ✨" })); };
    $("#chInput").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });
    $("#chSys").onclick = async () => {
      try {
        const d = await api("/api/prompts/compile", { method: "POST", body: { hierarchy: P.h, untrusted_context: $("#chCtx").value } });
        drawer("System prompt sent to the model", h("p", { class: "muted small", text: `~${d.tokens} tokens` }), h("pre", { class: "compiled", text: d.system || "(empty)" }));
      } catch (e) { toast(e.message, "err"); }
    };
  }
  await loadChatBackends();
}
async function loadChatBackends() {
  try { Chat.backends = (await api("/api/backends")).backends; } catch (e) { return toast(e.message, "err"); }
  if (!M.all.length) await loadModels().catch(() => {});
  const sel = $("#chBackend"), prev = sel.value;
  sel.replaceChildren(...Chat.backends.map((b) => h("option", { value: b.id, text: `${b.online ? "● " : "○ "}${b.label}${b.online ? "" : b.kind === "llama_cpp" || b.kind === "transformers" ? " (not installed)" : " (offline)"}` })));
  const firstOnline = Chat.backends.find((b) => b.online && b.models.length) || Chat.backends.find((b) => b.online);
  sel.value = Chat.backends.some((b) => b.id === prev) ? prev : (firstOnline || Chat.backends[0]).id;
  fillModels();
  applyPending();
}
function fillModels() {
  const b = Chat.backends.find((x) => x.id === $("#chBackend").value); if (!b) return;
  let opts = [];
  if (b.kind === "ollama" || b.kind === "openai") opts = b.models.map((m) => h("option", { value: m, text: m }));
  else if (b.kind === "llama_cpp") opts = M.all.filter((m) => m.format === "GGUF" || m.format === "Ollama").map((m) => h("option", { value: m.id, text: `${m.name} (${fmtBytes(m.size)})` }));
  else opts = M.all.filter((m) => m.format === "HF Transformers").map((m) => h("option", { value: m.id, text: `${m.name} (${fmtBytes(m.size)})` }));
  if (!opts.length) opts = [h("option", { value: "", text: "no models available" })];
  $("#chModel").replaceChildren(...opts);
  const hints = {
    ollama: !b.online ? "Ollama isn't running. Install it from ollama.com and run `ollama serve`."
      : b.models.length ? "" : "Ollama is running but has no models yet. Try: ollama pull llama3.2",
    openai: b.online ? "" : "Server not reachable. Start it or edit the endpoint in Settings.",
    llama_cpp: b.hint || "Runs a scanned GGUF in-process. First message loads the model.",
    transformers: b.hint || "Runs a scanned Hugging Face folder in-process (needs enough RAM/VRAM).",
  };
  $("#chHint").textContent = hints[b.kind] || "";
}
function applyPending() {
  const p = Chat.pending; if (!p || !Chat.backends.length) return;
  const b = Chat.backends.find((x) => x.kind === p.kind); if (!b) return;
  $("#chBackend").value = b.id; fillModels();
  $("#chModel").value = p.model || p.model_id || ""; Chat.pending = null;
}
function backendSpec() {
  const b = Chat.backends.find((x) => x.id === $("#chBackend").value), model = $("#chModel").value;
  if (!b || !model) return null;
  if (b.kind === "ollama") return { kind: "ollama", model };
  if (b.kind === "openai") return { kind: "openai", endpoint: b.endpoint, model };
  return { kind: b.kind, model_id: model };
}
function inline(text, el) {
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g; let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) el.append(text.slice(last, m.index));
    const tok = m[0];
    el.append(tok[0] === "`" ? h("code", { text: tok.slice(1, -1) }) : h("strong", { text: tok.slice(2, -2) }));
    last = m.index + tok.length;
  }
  if (last < text.length) el.append(text.slice(last));
}
function renderMd(text, into) {
  into.textContent = "";
  text.split("```").forEach((part, i) => {
    if (i % 2) { const nl = part.indexOf("\n"); into.append(h("pre", {}, h("code", { text: (nl >= 0 ? part.slice(nl + 1) : part).replace(/\n$/, "") }))); }
    else part.split(/\n{2,}/).forEach((para) => { if (para.trim()) { const p = h("p"); inline(para, p); into.append(p); } });
  });
}
function addMsg(role, text) {
  const box = $("#msgs"); box.querySelector(".empty")?.remove();
  const el = h("div", { class: "msg " + role }); if (text) renderMd(text, el);
  box.append(el); box.scrollTop = box.scrollHeight; return el;
}
async function sendChat() {
  if (Chat.ctrl) return;
  const input = $("#chInput"), text = input.value.trim(); if (!text) return;
  const spec = backendSpec(); if (!spec) return toast("Choose a backend and model first", "err");
  input.value = ""; Chat.messages.push({ role: "user", content: text }); addMsg("user", text);
  const el = addMsg("assistant", ""); el.classList.add("cursor"); let acc = "", raf = 0;
  const paint = () => { raf = 0; renderMd(acc, el); const b = $("#msgs"); if (b.scrollHeight - b.scrollTop - b.clientHeight < 140) b.scrollTop = b.scrollHeight; };
  Chat.ctrl = new AbortController(); $("#chSend").hidden = true; $("#chStop").hidden = false;
  try {
    const r = await fetch("/api/chat", {
      method: "POST", signal: Chat.ctrl.signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        backend: spec, messages: Chat.messages, hierarchy: P.h, untrusted_context: $("#chCtx").value,
        params: { temperature: +$("#chTemp").value, top_p: +$("#chTopP").value, max_tokens: $("#chMax").value ? +$("#chMax").value : null },
      }),
    });
    if (!r.ok) { let d; try { d = (await r.json()).detail; } catch { /* */ } throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || r.statusText); }
    const reader = r.body.getReader(), dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 2);
        if (!line.startsWith("data:")) continue;
        const ev = JSON.parse(line.slice(5));
        if (ev.type === "delta") { acc += ev.text; if (!raf) raf = requestAnimationFrame(paint); }
        else if (ev.type === "error") { el.classList.add("err"); acc += (acc ? "\n\n" : "") + "⚠ " + ev.message; }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") { el.classList.add("err"); acc += (acc ? "\n\n" : "") + "⚠ " + e.message; }
  } finally {
    cancelAnimationFrame(raf); el.classList.remove("cursor"); renderMd(acc || "(no output)", el);
    if (acc && !el.classList.contains("err")) Chat.messages.push({ role: "assistant", content: acc });
    else Chat.messages.pop(); // empty or error reply: drop the unanswered user turn so errors aren't fed back as history
    Chat.ctrl = null; $("#chSend").hidden = false; $("#chStop").hidden = true; input.focus();
  }
}

/* ---------- libraries ---------- */
const L = { all: [], q: "", job: null };
async function loadLibs() {
  try { L.all = (await api("/api/libraries")).libraries; } catch (e) { return toast(e.message, "err"); }
  renderLibs();
}
function renderLibs() {
  const q = L.q.toLowerCase(), box = $("#libGrid"); box.textContent = "";
  const rows = L.all.filter((l) => !q || (l.pip + l.desc + l.category).toLowerCase().includes(q));
  $("#libCount").textContent = `${L.all.filter((l) => l.installed).length} / ${L.all.filter((l) => l.applicable).length} installed`;
  const cats = [...new Set(rows.map((l) => l.category))];
  for (const c of cats) {
    box.append(h("div", { class: "lib-cat", text: c }));
    box.append(h("div", { class: "libs" }, rows.filter((l) => l.category === c).map((l) =>
      h("div", { class: "lib" },
        h("div", { class: "top2" }, h("b", { text: l.pip }),
          l.installed ? h("span", { class: "chip ok", text: "✓ " + (l.version || "") })
            : !l.applicable ? h("span", { class: "chip", text: "n/a on this OS" }) : h("span", { class: "chip", text: "not installed" })),
        h("p", { text: l.desc }),
        l.applicable && !l.installed ? h("button", { class: "btn sm", disabled: !!L.job, text: "Install", onclick: () => runInstall({ packages: [l.pip] }) }) : null))));
  }
}
$("#libSearch").oninput = debounce((e) => { L.q = e.target.value; renderLibs(); }, 100);
$$("[data-profile]").forEach((b) => { b.onclick = () => {
  const p = b.dataset.profile;
  if (p === "full" && !confirm("This installs every library (several GB; some need a C++ compiler and may fail — failures are skipped). Continue?")) return;
  runInstall({ profile: p });
}; });
async function runInstall(body) {
  if (L.job) return;
  let r;
  try { r = await api("/api/libraries/install", { method: "POST", body }); } catch (e) { return toast(e.message, "err"); }
  if (!r.job) return toast(r.message, "ok");
  L.job = r.job; renderLibs();
  const log = $("#jobLog"); log.hidden = false; log.textContent = `Installing ${r.packages.join(", ")}…\n`;
  let since = 0;
  const tick = async () => {
    try {
      const j = await api(`/api/jobs/${L.job}?since=${since}`); since = j.next;
      if (j.lines.length) { log.textContent += j.lines.join("\n") + "\n"; log.scrollTop = log.scrollHeight; }
      if (j.running) return setTimeout(tick, 1000);
      const ok = Object.values(j.results).filter(Boolean).length, bad = Object.values(j.results).length - ok;
      toast(`Install finished: ${ok} ok${bad ? `, ${bad} failed (see log)` : ""}`, bad ? "err" : "ok");
    } catch (e) { toast(e.message, "err"); }
    L.job = null; loadLibs();
  };
  tick();
}

/* ---------- system ---------- */
async function loadSystem(deep = false) {
  let s;
  try { s = await api("/api/system" + (deep ? "?deep=true" : "")); } catch (e) { return toast(e.message, "err"); }
  const stat = (b, t) => h("div", { class: "stat" }, h("b", { text: b }), h("span", { text: t }));
  $("#sysStats").replaceChildren(
    stat(s.platform.split("-").slice(0, 2).join(" "), "operating system"), stat("Python " + s.python, s.machine), stat(s.cpu_count, "CPU threads"),
    s.memory ? stat(fmtBytes(s.memory.total), `RAM · ${fmtBytes(s.memory.available)} free`) : stat("—", "RAM (install psutil)"),
    s.disk ? stat(fmtBytes(s.disk.free), `free on ${s.disk.path}`) : stat("—", "disk"),
    stat(s.gpus.length || "none", s.gpus.length ? s.gpus.map((g) => g.name).join(", ") : "NVIDIA GPUs detected"));
  const d = $("#sysDetail"); d.textContent = "";
  d.append(h("div", { class: "card" }, h("h3", { text: "Environment" }), kvTable({ Interpreter: s.executable, "Data directory": s.data_dir, Platform: s.platform })));
  if (s.gpus.length) d.append(h("div", { class: "card" }, h("h3", { text: "GPUs" }), ...s.gpus.map((g) => kvTable({ Name: g.name, VRAM: g.memory_mb ? fmtBytes(g.memory_mb * 1048576) : "?", Driver: g.driver }))));
  if (s.frameworks) for (const [k, v] of Object.entries(s.frameworks)) d.append(h("div", { class: "card" }, h("h3", { text: k }), kvTable(v)));
  else if (deep) d.append(h("div", { class: "card muted", text: "No PyTorch / TensorFlow / JAX installed yet — see the Libraries tab." }));
}
$("#deepBtn").onclick = async (e) => { e.target.disabled = true; e.target.textContent = "Probing…"; await loadSystem(true); e.target.disabled = false; e.target.textContent = "Probe PyTorch / TensorFlow / JAX"; };

/* ---------- settings ---------- */
let eps = [];
function renderEps() {
  $("#epList").replaceChildren(...eps.map((ep, i) => h("div", { class: "row wrap", style: "margin-bottom:8px" },
    h("input", { value: ep.name, placeholder: "Name", style: "flex:1;min-width:120px", oninput: (e) => { ep.name = e.target.value; } }),
    h("input", { value: ep.base_url, placeholder: "http://127.0.0.1:1234/v1", style: "flex:2;min-width:200px", oninput: (e) => { ep.base_url = e.target.value; } }),
    h("input", { value: ep.api_key, type: "password", placeholder: "API key (optional)", style: "flex:1;min-width:120px", oninput: (e) => { ep.api_key = e.target.value; } }),
    h("button", { class: "btn sm danger", text: "Remove", onclick: () => { eps.splice(i, 1); renderEps(); } }))));
}
async function loadSettings() {
  try {
    const s = await api("/api/settings");
    $("#setRoots").value = s.extra_roots.join("\n"); $("#setOllama").value = s.ollama_url;
    eps = s.openai_endpoints.map((e) => ({ ...e })); renderEps();
    const sys = await api("/api/system"); $("#dataDir").textContent = "Data: " + sys.data_dir;
  } catch (e) { toast(e.message, "err"); }
  T.refresh();
}
$("#epAdd").onclick = () => { eps.push({ name: "My server", base_url: "http://127.0.0.1:8000/v1", api_key: "" }); renderEps(); };
$("#setSave").onclick = async () => {
  try {
    await api("/api/settings", { method: "PUT", body: { extra_roots: $("#setRoots").value.split("\n").map((x) => x.trim()).filter(Boolean), ollama_url: $("#setOllama").value.trim(), openai_endpoints: eps } });
    toast("Settings saved", "ok"); chatReady && loadChatBackends();
  } catch (e) { toast(e.message, "err"); }
};

/* ---------- boot ---------- */
paintIcons();
route();
api("/api/health").then((d) => { $("#ver").textContent = "v" + d.version; }).catch(() => {});
api("/api/scan").then((s) => { paintScan(s); if (s.running) pollScan(true); }).catch(() => {});
loadModels().catch((e) => toast(e.message, "err"));
})();
