/*
 * Arqade theme engine. Loaded synchronously in <head> so the first paint is already correct.
 *
 * Default is DARK. Users can pick light. If a "dark mode" browser extension is active
 * (Dark Reader, Night Eye, Midnight Lizard, Turn Off the Lights, ...) the page switches its
 * own base theme to LIGHT, so the extension darkens a light page instead of re-inverting a
 * page that is already dark. Detection is heuristic and re-runs when the DOM changes, so
 * disabling the extension flips the page back to dark.
 *
 * To teach it a new extension, add a selector to EXT_SELECTORS or a regex to ATTR_RE.
 */
(function () {
  "use strict";
  var root = document.documentElement;
  var KEY = "arqade.theme", GUARD = "arqade.guard", OVERRIDE = "arqade.override";
  var listeners = [];

  var EXT_SELECTORS = [
    'meta[name="darkreader"]', 'style.darkreader', 'style[class*="darkreader"]',
    '[data-darkreader-mode]', '[data-darkreader-scheme]', 'link[class*="darkreader"]',
    'html[nighteyeplugin]', 'style[class*="nighteye"]', 'style[id*="nighteye"]', '[class*="nighteyeplugin"]',
    'style[id*="mlstyle"]', 'style[class*="mlstyle"]', '[id^="midnight-lizard"]', 'html[ml-scheme]',
    'style[id*="dark-mode-ext"]', '[class*="stefanvd-lightsoff"]', '[id*="stefanvdlightsoff"]',
    'style[data-dark-mode-extension]', 'style[id^="super-dark"]', 'style[class*="super-dark"]',
    'style[id*="dark-theme-extension"]'
  ].join(",");
  var ATTR_RE = /^(data-)?(darkreader|nighteye|ml-|midnight|stefanvd|super-?dark|nightmode)/i;
  var NAMES = [
    [/darkreader/i, "Dark Reader"], [/nighteye/i, "Night Eye"], [/midnight|ml-?(style|scheme)/i, "Midnight Lizard"],
    [/stefanvd|lightsoff/i, "Turn Off the Lights"], [/super-?dark/i, "Super Dark Mode"]
  ];

  function safe(fn, fallback) { try { return fn(); } catch (e) { return fallback; } }
  function get(k, d) { return safe(function () { var v = localStorage.getItem(k); return v === null ? d : v; }, d); }
  function put(k, v) { safe(function () { localStorage.setItem(k, v); }); }

  function detect() {
    var hit = null;
    var attrs = root.attributes;
    for (var i = 0; i < attrs.length; i++) if (ATTR_RE.test(attrs[i].name)) { hit = attrs[i].name; break; }
    if (!hit) {
      var el = safe(function () { return document.querySelector(EXT_SELECTORS); }, null);
      if (el) hit = (el.getAttribute("name") || el.className || el.id || el.tagName || "") + "";
    }
    if (!hit) return "";
    for (var n = 0; n < NAMES.length; n++) if (NAMES[n][0].test(hit)) return NAMES[n][1];
    return "A dark-mode extension";
  }

  var state = { pref: "dark", guard: true, override: false, detected: "", effective: "dark" };

  function compute() {
    state.pref = get(KEY, "dark") === "light" ? "light" : "dark";
    state.guard = get(GUARD, "1") !== "0";
    state.override = safe(function () { return sessionStorage.getItem(OVERRIDE) === "1"; }, false);
    state.detected = detect();
    var autoLight = state.pref === "dark" && state.guard && !!state.detected && !state.override;
    state.effective = autoLight ? "light" : state.pref;
    state.autoLight = autoLight;
  }

  function apply() {
    var before = state.effective + "|" + state.detected + "|" + state.autoLight;
    compute();
    root.setAttribute("data-theme", state.effective);
    root.setAttribute("data-ext-detected", state.detected ? "1" : "0");
    var after = state.effective + "|" + state.detected + "|" + state.autoLight;
    if (before !== after) listeners.forEach(function (fn) { safe(function () { fn(state); }); });
  }

  var timer = null;
  function schedule() { clearTimeout(timer); timer = setTimeout(apply, 120); }

  window.ArqadeTheme = {
    state: function () { return state; },
    onChange: function (fn) { listeners.push(fn); fn(state); },
    /** Flip the theme the user is *seeing* and make that choice stick for this session. */
    toggle: function () {
      put(KEY, state.effective === "dark" ? "light" : "dark");
      safe(function () { sessionStorage.setItem(OVERRIDE, "1"); });
      apply();
    },
    setPref: function (pref) {
      put(KEY, pref === "light" ? "light" : "dark");
      safe(function () { sessionStorage.removeItem(OVERRIDE); });
      apply();
    },
    setGuard: function (on) {
      put(GUARD, on ? "1" : "0");
      safe(function () { sessionStorage.removeItem(OVERRIDE); });
      apply();
    },
    refresh: apply
  };

  apply();
  if (window.MutationObserver) {
    var mo = new MutationObserver(schedule);
    mo.observe(root, { attributes: true, childList: true });
    var watchHead = function () { if (document.head) mo.observe(document.head, { childList: true }); };
    watchHead();
    document.addEventListener("DOMContentLoaded", function () { watchHead(); schedule(); });
  }
  // Cheap safety net for extensions that inject late or detach silently.
  setInterval(apply, 4000);
})();
