"use strict";
/* Studio: non-destructive editing and mixing, rendered by SoundCraft on the server.
   Uses helpers from app.js: $, $$, api, esc, cssVar, state, replaceSong, renderSongs, poll. */

const studio = {
  info: null,          // /api/studio: availability, plugins, processes, fade shapes
  song: null,
  doc: null,
  tracks: [],
  peaks: [],
  duration: 0,
  render: null,
  undo: [],
  redo: [],
  sel: null,           // {start, end} in seconds, or null
  playhead: 0,
  openInserts: new Set(),
  fxParams: {},
  seq: 0,
  version: 0,         // bumped on every local change; stale renders are ignored
  rendering: false,
  pending: false,
  timer: null,
};

const UNIT = { Db: "dB", Hz: "Hz", Ms: "ms", Percent: "%", Seconds: "s", Ratio: ":1", Semitones: "st", Cents: "ct" };
const LOUDNESS = [["", "Off"], ["-16", "−16 LUFS (quiet)"], ["-14", "−14 LUFS (streaming)"], ["-11", "−11 LUFS (loud)"], ["-9", "−9 LUFS (very loud)"]];

const fmtT = s => {
  s = Math.max(0, s || 0);
  const m = Math.floor(s / 60), r = s - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
};
const plugin = id => studio.info.plugins.find(p => p.id === id);
const pluginName = id => plugin(id)?.name || id;
const clone = o => JSON.parse(JSON.stringify(o));

// ------------------------------------------------------------------ open / close
async function openStudio(song) {
  closeMenu?.();
  const box = $("#studio");
  box.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  $("#st-title").textContent = song.title;
  studio.song = song;
  studio.version++;
  studio.undo = []; studio.redo = []; studio.sel = null; studio.playhead = 0; studio.openInserts.clear();
  $("#st-audio").pause();
  $("#st-target").value = "";
  if (!studio.info) studio.info = await api("/api/studio");
  const missing = $("#st-missing");
  if (!studio.info.available) {
    $("#st-body").classList.add("hidden");
    missing.classList.remove("hidden");
    missing.innerHTML = `<h3>Studio needs SoundCraft</h3>
      <p>MusicMake edits and mixes with <a href="https://github.com/storytold/soundcraft" target="_blank" rel="noopener">SoundCraft</a>,
      an open-source audio workstation. Install its command-line tool, then restart MusicMake:</p>
      <p><code>cargo install --git https://github.com/storytold/soundcraft soundcraft-cli</code></p>
      <p class="muted small">${esc(studio.info.detail)}</p>`;
    return;
  }
  missing.classList.add("hidden");
  $("#st-body").classList.remove("hidden");
  setupStudioOnce();
  setStatus("Loading…", "busy");
  try {
    applyState(await api(`/api/songs/${song.id}/studio`));
    setStatus(studio.render ? "" : "Original audio. Make an edit or change the mix to hear it through SoundCraft.");
  } catch (e) {
    setStatus(e.message, "err");
  }
}

function closeStudio() {
  $("#studio").classList.add("hidden");
  document.body.style.overflow = "";
  $("#st-audio").pause();
  studio.song = null;
}

function applyState(s) {
  studio.doc = s.doc;
  studio.tracks = s.tracks;
  studio.peaks = s.peaks;
  studio.duration = s.duration;
  studio.render = s.render;
  if (studio.sel) {
    studio.sel.end = Math.min(studio.sel.end, s.duration);
    if (studio.sel.end - studio.sel.start < 0.01) studio.sel = null;
  }
  studio.playhead = Math.min(studio.playhead, s.duration);
  const src = $("#st-source");
  $("#st-source-wrap").classList.toggle("hidden", !s.has_stems);
  src.value = s.doc.source;
  const tgt = $("#st-target"), keep = tgt.value;
  tgt.innerHTML = `<option value="">All tracks</option>` + s.tracks.map(t => `<option>${esc(t)}</option>`).join("");
  if (s.tracks.includes(keep)) tgt.value = keep;
  const audio = $("#st-audio");
  const wasPlaying = !audio.paused;
  audio.src = (s.preview ? `/api/songs/${studio.song.id}/studio/preview` : `/api/songs/${studio.song.id}/audio`) + `?v=${Date.now()}`;
  audio.addEventListener("loadedmetadata", () => {
    audio.currentTime = Math.min(studio.playhead, audio.duration || 0);
    if (wasPlaying) audio.play();
  }, { once: true });
  $("#st-session").href = `/api/songs/${studio.song.id}/studio/session.zip`;
  drawStudio();
  renderMixer();
  renderEdits();
  syncSelInputs();
  $("#st-undo").disabled = !studio.undo.length;
  $("#st-redo").disabled = !studio.redo.length;
  $("#st-len").textContent = fmtT(s.duration);
}

function setStatus(text, kind = "") {
  const el = $("#st-status");
  el.className = "st-status small " + (kind || "muted");
  if (!text && studio.render) {
    const r = studio.render;
    const parts = [`Rendered by SoundCraft`, `${r.lufs > -100 ? r.lufs.toFixed(1) : "–∞"} LUFS`,
      `peak ${r.peak_db.toFixed(1)} dB`, `true peak ${r.true_peak_db.toFixed(1)} dBTP`];
    if (r.loudness_gain_db) parts.push(`loudness gain ${r.loudness_gain_db > 0 ? "+" : ""}${r.loudness_gain_db.toFixed(1)} dB`);
    text = parts.join(" · ");
  }
  el.textContent = text;
}

// ------------------------------------------------------------------ changes & rendering
function change(mutator, { now = false } = {}) {
  studio.version++;
  studio.undo.push(clone(studio.doc));
  if (studio.undo.length > 100) studio.undo.shift();
  studio.redo = [];
  mutator(studio.doc);
  renderMixer(); renderEdits();
  $("#st-undo").disabled = false; $("#st-redo").disabled = true;
  scheduleRender(now ? 0 : 450);
}

function scheduleRender(delay) {
  clearTimeout(studio.timer);
  studio.timer = setTimeout(doRender, delay);
}

async function doRender() {
  if (!studio.song) return;
  if (studio.rendering) { studio.pending = true; return; }
  studio.rendering = true;
  const seq = ++studio.seq, version = studio.version;
  setStatus("Rendering in SoundCraft…", "busy");
  try {
    const s = await api(`/api/songs/${studio.song.id}/studio/render`, { method: "POST", body: { doc: studio.doc } });
    // Only show this render if nothing changed while it ran; otherwise the next one is coming.
    if (seq === studio.seq && version === studio.version && studio.song) { applyState(s); setStatus(""); }
  } catch (e) {
    setStatus(e.message, "err");
  } finally {
    studio.rendering = false;
    if (studio.pending) { studio.pending = false; doRender(); }
  }
}

function undoStudio() {
  if (!studio.undo.length) return;
  studio.version++;
  studio.redo.push(clone(studio.doc));
  studio.doc = studio.undo.pop();
  renderMixer(); renderEdits();
  scheduleRender(0);
}
function redoStudio() {
  if (!studio.redo.length) return;
  studio.version++;
  studio.undo.push(clone(studio.doc));
  studio.doc = studio.redo.pop();
  renderMixer(); renderEdits();
  scheduleRender(0);
}

// ------------------------------------------------------------------ timeline
function drawStudio() {
  const canvas = $("#st-wave");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w) return;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const dur = studio.duration || 1, ruler = 18, mid = ruler + (h - ruler) / 2, amp = (h - ruler) / 2 - 4;
  const x = t => (t / dur) * w;
  // ruler
  ctx.fillStyle = cssVar("--muted");
  ctx.font = "11px system-ui, sans-serif";
  const step = [1, 2, 5, 10, 15, 30, 60, 120].find(s => (s / dur) * w > 70) || 300;
  for (let t = 0; t <= dur; t += step) {
    ctx.fillRect(x(t), 0, 1, 6);
    ctx.fillText(fmt(t), x(t) + 3, 12);
  }
  // selection
  if (studio.sel) {
    ctx.fillStyle = cssVar("--accent-soft");
    ctx.fillRect(x(studio.sel.start), ruler, Math.max(1, x(studio.sel.end) - x(studio.sel.start)), h - ruler);
  }
  // waveform
  const peaks = studio.peaks || [];
  const n = peaks.length;
  ctx.fillStyle = cssVar("--wave-on");
  for (let i = 0; i < w; i++) {
    const v = peaks[Math.floor((i / w) * n)] || 0;
    const bh = Math.max(1, v * amp);
    ctx.fillRect(i, mid - bh, 1, bh * 2);
  }
  // playhead
  ctx.fillStyle = cssVar("--ink");
  ctx.fillRect(x(studio.playhead), ruler - 4, 2, h - ruler + 4);
}

function setupTimeline() {
  const canvas = $("#st-wave");
  let down = null;
  const toT = ev => {
    const r = canvas.getBoundingClientRect();
    return Math.min(Math.max(0, ((ev.clientX - r.left) / r.width) * studio.duration), studio.duration);
  };
  canvas.addEventListener("pointerdown", ev => {
    canvas.setPointerCapture(ev.pointerId);
    down = toT(ev);
    studio.sel = null;
  });
  canvas.addEventListener("pointermove", ev => {
    if (down === null) return;
    const t = toT(ev);
    if (Math.abs(t - down) * (canvas.clientWidth / studio.duration) > 3) {
      studio.sel = { start: Math.min(down, t), end: Math.max(down, t) };
      syncSelInputs(); drawStudio();
    }
  });
  canvas.addEventListener("pointerup", ev => {
    if (down === null) return;
    if (!studio.sel) seekStudio(toT(ev));
    down = null;
    syncSelInputs(); drawStudio();
  });
  window.addEventListener("resize", () => { if (studio.song) drawStudio(); });
}

function syncSelInputs() {
  $("#st-sel-start").value = studio.sel ? studio.sel.start.toFixed(2) : "";
  $("#st-sel-end").value = studio.sel ? studio.sel.end.toFixed(2) : "";
}

function seekStudio(t) {
  studio.playhead = t;
  const a = $("#st-audio");
  if (a.duration) a.currentTime = Math.min(t, a.duration);
  $("#st-cur").textContent = fmtT(t);
  drawStudio();
}

// ------------------------------------------------------------------ edit tools
function needSel() {
  if (!studio.sel || studio.sel.end - studio.sel.start < 0.01) {
    setStatus("Select a range first: drag across the waveform.", "err");
    return null;
  }
  return { start: +studio.sel.start.toFixed(3), end: +studio.sel.end.toFixed(3) };
}
function targetTracks() { const v = $("#st-target").value; return v ? [v] : null; }

function addEdit(edit, { clearSel = false } = {}) {
  change(doc => doc.edits.push(edit), { now: true });
  if (clearSel) { studio.sel = null; syncSelInputs(); drawStudio(); }
}

function setupTools() {
  $$("[data-op]").forEach(b => b.addEventListener("click", () => {
    const sel = needSel(); if (!sel) return;
    const op = b.dataset.op;
    const e = { op, ...sel };
    if (op === "gain") e.db = +$("#st-gain").value || 0;
    if (op === "silence" || op === "gain") { const t = targetTracks(); if (t) e.tracks = t; }
    addEdit(e, { clearSel: op === "cut" || op === "keep" });
  }));
  $$("[data-proc]").forEach(b => b.addEventListener("click", () => {
    const sel = needSel(); if (!sel) return;
    const e = { op: "process", process: b.dataset.proc, ...sel };
    if (e.process === "pitch_shift") e.params = { semitones: +$("#st-semi").value || 0 };
    const t = targetTracks(); if (t) e.tracks = t;
    addEdit(e);
  }));
  $$("[data-fade]").forEach(b => b.addEventListener("click", () => {
    const e = { op: b.dataset.fade, length: Math.max(0.1, +$("#st-fade").value || 2), shape: $("#st-fade-shape").value };
    const t = targetTracks(); if (t) e.tracks = t;
    addEdit(e);
  }));
  const fx = $("#st-fx");
  fx.innerHTML = studio.info.plugins.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  fx.value = "room_reverb";
  fx.addEventListener("change", () => { studio.fxParams = {}; if (!$("#st-fx-params").classList.contains("hidden")) showFxParams(); });
  $("#st-fx-edit").addEventListener("click", () => {
    const box = $("#st-fx-params");
    if (box.classList.toggle("hidden")) return;
    showFxParams();
  });
  $("#st-fx-apply").addEventListener("click", () => {
    const sel = needSel(); if (!sel) return;
    const e = { op: "process", process: fx.value, params: { ...studio.fxParams }, ...sel };
    const t = targetTracks(); if (t) e.tracks = t;
    addEdit(e);
  });
  $("#st-fade-shape").innerHTML = studio.info.fade_shapes.map(s => `<option ${s === "s-curve" ? "selected" : ""}>${s}</option>`).join("");
}

function showFxParams() {
  const box = $("#st-fx-params");
  const id = $("#st-fx").value;
  box.innerHTML = `<div class="muted small" style="margin-bottom:6px">${esc(pluginName(id))} settings for <b>Apply effect</b></div>`;
  box.append(paramEditor(id, studio.fxParams, (k, v) => { studio.fxParams[k] = v; }));
}

function setupSelectionInputs() {
  const upd = () => {
    const a = parseFloat($("#st-sel-start").value), b = parseFloat($("#st-sel-end").value);
    if (isFinite(a) && isFinite(b) && b > a) {
      studio.sel = { start: Math.max(0, a), end: Math.min(studio.duration, b) };
      drawStudio();
    }
  };
  $("#st-sel-start").addEventListener("change", upd);
  $("#st-sel-end").addEventListener("change", upd);
  $("#st-sel-all").addEventListener("click", () => { studio.sel = { start: 0, end: studio.duration }; syncSelInputs(); drawStudio(); });
  $("#st-sel-none").addEventListener("click", () => { studio.sel = null; syncSelInputs(); drawStudio(); });
}

// ------------------------------------------------------------------ edit list
function describeEdit(e) {
  const range = e.start !== undefined ? `${fmtT(e.start)}–${fmtT(e.end)}` : "";
  const on = e.tracks ? ` on ${e.tracks.join(", ")}` : "";
  switch (e.op) {
    case "cut": return `Cut ${range}`;
    case "keep": return `Keep only ${range}`;
    case "silence": return `Silence ${range}${on}`;
    case "gain": return `Gain ${e.db > 0 ? "+" : ""}${e.db} dB ${range}${on}`;
    case "fade_in": return `Fade in ${e.length}s (${e.shape})${on}`;
    case "fade_out": return `Fade out ${e.length}s (${e.shape})${on}`;
    case "process": {
      const name = { reverse: "Reverse", normalize: "Normalize", invert: "Invert",
        pitch_shift: `Pitch ${(e.params?.semitones > 0 ? "+" : "") + (e.params?.semitones ?? 0)} st` }[e.process] || pluginName(e.process);
      return `${name} ${range}${on}`;
    }
  }
  return e.op;
}

function renderEdits() {
  const list = $("#st-edit-list");
  const edits = studio.doc?.edits || [];
  $("#st-no-edits").classList.toggle("hidden", edits.length > 0);
  list.innerHTML = "";
  edits.forEach((e, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${esc(describeEdit(e))}</span><button aria-label="Remove this edit" title="Remove">✕</button>`;
    $("button", li).addEventListener("click", () => change(doc => doc.edits.splice(i, 1), { now: true }));
    list.append(li);
  });
}

// ------------------------------------------------------------------ mixer
function slider({ label, min, max, step, value, fmt: f, onInput, log = false }) {
  const row = document.createElement("label");
  row.className = "ctl";
  const toPos = v => log ? Math.log(v / min) / Math.log(max / min) * 1000 : v;
  const fromPos = p => log ? min * Math.pow(max / min, p / 1000) : p;
  row.innerHTML = `<span>${esc(label)}</span><input type="range"><output></output>`;
  const input = $("input", row), out = $("output", row);
  if (log) { input.min = 0; input.max = 1000; input.step = 1; } else { input.min = min; input.max = max; input.step = step; }
  input.value = toPos(value);
  out.textContent = f(value);
  input.addEventListener("input", () => { const v = fromPos(+input.value); out.textContent = f(v); onInput(v, false); });
  input.addEventListener("change", () => onInput(fromPos(+input.value), true));
  return row;
}

function paramEditor(pid, params, onSet) {
  const wrap = document.createElement("div");
  wrap.className = "params";
  for (const q of plugin(pid).params) {
    const val = params[q.id] ?? q.default;
    if (q.unit === "Toggle") {
      const row = document.createElement("label");
      row.className = "ctl";
      row.innerHTML = `<span>${esc(q.name)}</span><input type="checkbox" ${val >= 0.5 ? "checked" : ""}><output></output>`;
      $("input", row).addEventListener("change", ev => onSet(q.id, ev.target.checked ? 1 : 0, true));
      wrap.append(row);
    } else if (q.unit === "Choice" && q.choices?.length) {
      const row = document.createElement("label");
      row.className = "ctl";
      row.innerHTML = `<span>${esc(q.name)}</span><select>${q.choices.map((c, i) => `<option value="${i}" ${Math.round(val) === i ? "selected" : ""}>${esc(c)}</option>`).join("")}</select><output></output>`;
      $("select", row).addEventListener("change", ev => onSet(q.id, +ev.target.value, true));
      wrap.append(row);
    } else {
      const log = q.unit === "Hz" && q.min > 0;
      const unit = UNIT[q.unit] || "";
      const span = q.max - q.min;
      const digits = span <= 2 ? 2 : span <= 30 ? 1 : 0;
      wrap.append(slider({
        label: q.name, min: q.min, max: q.max, step: span / 200, value: val, log,
        fmt: v => (q.unit === "Hz" && v >= 1000 ? (v / 1000).toFixed(1) + "k" : v.toFixed(digits)) + unit,
        onInput: (v, done) => onSet(q.id, +v.toFixed(4), done),
      }));
    }
  }
  return wrap;
}

function insertsEditor(owner, key) {
  const box = document.createElement("div");
  box.className = "inserts";
  owner.inserts.forEach((ins, i) => {
    const el = document.createElement("div");
    const openKey = `${key}:${i}`;
    el.className = "insert" + (ins.bypass ? " bypassed" : "");
    el.innerHTML = `<div class="insert-head"><span class="name" title="Show settings">${esc(pluginName(ins.plugin))}</span>
      <button class="byp" title="${ins.bypass ? "Turn on" : "Bypass"}">${ins.bypass ? "○" : "●"}</button>
      <button class="up" title="Move up">↑</button><button class="rm" title="Remove">✕</button></div>`;
    $(".name", el).addEventListener("click", () => {
      studio.openInserts.has(openKey) ? studio.openInserts.delete(openKey) : studio.openInserts.add(openKey);
      renderMixer();
    });
    $(".byp", el).addEventListener("click", () => change(() => { ins.bypass = !ins.bypass; }));
    $(".rm", el).addEventListener("click", () => { studio.openInserts.clear(); change(() => owner.inserts.splice(i, 1), { now: true }); });
    $(".up", el).addEventListener("click", () => {
      if (!i) return;
      studio.openInserts.clear();
      change(() => owner.inserts.splice(i - 1, 0, owner.inserts.splice(i, 1)[0]), { now: true });
    });
    if (studio.openInserts.has(openKey)) {
      el.append(paramEditor(ins.plugin, ins.params, (k, v, done) => {
        if (!done) return;
        change(() => { ins.params[k] = v; });
      }));
    }
    box.append(el);
  });
  const max = key === "master" ? 8 : 10;
  if (owner.inserts.length < max) {
    const add = document.createElement("select");
    add.className = "add-fx";
    add.innerHTML = `<option value="">+ Add effect…</option>` +
      [...new Set(studio.info.plugins.map(p => p.category))].map(cat =>
        `<optgroup label="${esc(cat)}">${studio.info.plugins.filter(p => p.category === cat).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</optgroup>`).join("");
    add.addEventListener("change", () => {
      if (!add.value) return;
      const pid = add.value;
      studio.openInserts.add(`${key}:${owner.inserts.length}`);
      change(() => owner.inserts.push({ plugin: pid, params: {}, bypass: false }), { now: true });
    });
    box.append(add);
  }
  return box;
}

function renderMixer() {
  const mixer = $("#st-mixer");
  if (!studio.doc) return;
  mixer.innerHTML = "";
  const dB = v => (v > 0 ? "+" : "") + v.toFixed(1) + " dB";
  const panF = v => Math.abs(v) < 0.005 ? "C" : (v < 0 ? "L" : "R") + Math.round(Math.abs(v) * 100);
  for (const t of studio.doc.tracks) {
    const strip = document.createElement("div");
    strip.className = "strip";
    strip.innerHTML = `<div class="strip-head"><span class="strip-name" title="${esc(t.name)}">${esc(t.name === "song" ? "Full mix" : t.name)}</span>
      <span class="ms"><button class="m ${t.mute ? "on" : ""}" title="Mute" aria-pressed="${t.mute}">M</button><button class="s ${t.solo ? "on" : ""}" title="Solo" aria-pressed="${t.solo}">S</button></span></div>`;
    $(".m", strip).addEventListener("click", () => change(() => { t.mute = !t.mute; }, { now: true }));
    $(".s", strip).addEventListener("click", () => change(() => { t.solo = !t.solo; }, { now: true }));
    strip.append(slider({ label: "Volume", min: -30, max: 12, step: 0.5, value: t.volume_db, fmt: dB,
      onInput: (v, done) => done && change(() => { t.volume_db = v; }) }));
    strip.append(slider({ label: "Pan", min: -1, max: 1, step: 0.01, value: t.pan, fmt: panF,
      onInput: (v, done) => done && change(() => { t.pan = v; }) }));
    strip.append(insertsEditor(t, t.name));
    mixer.append(strip);
  }
  const m = studio.doc.master;
  const strip = document.createElement("div");
  strip.className = "strip master";
  strip.innerHTML = `<div class="strip-head"><span class="strip-name">Master</span></div>`;
  strip.append(slider({ label: "Volume", min: -30, max: 12, step: 0.5, value: m.volume_db, fmt: dB,
    onInput: (v, done) => done && change(() => { m.volume_db = v; }) }));
  strip.append(insertsEditor(m, "master"));
  const loud = document.createElement("label");
  loud.className = "ctl";
  loud.innerHTML = `<span>Loudness</span><select class="loudness" aria-label="Loudness target">${LOUDNESS.map(([v, l]) => `<option value="${v}" ${String(m.loudness ?? "") === v ? "selected" : ""}>${l}</option>`).join("")}</select><output></output>`;
  $("select", loud).addEventListener("change", ev => change(() => { m.loudness = ev.target.value === "" ? null : +ev.target.value; }, { now: true }));
  strip.append(loud);
  const norm = document.createElement("label");
  norm.className = "ctl";
  norm.innerHTML = `<span>Normalize</span><input type="checkbox" ${m.normalize ? "checked" : ""}><output></output>`;
  $("input", norm).addEventListener("change", ev => change(() => { m.normalize = ev.target.checked; }, { now: true }));
  strip.append(norm);
  const meter = document.createElement("div");
  meter.className = "meter-line";
  meter.textContent = studio.render ? `${studio.render.lufs.toFixed(1)} LUFS · TP ${studio.render.true_peak_db.toFixed(1)} dBTP` : "Not rendered yet";
  strip.append(meter);
  $("#st-master").replaceChildren(strip);
}

// ------------------------------------------------------------------ transport & actions
let studioReady = false;
function setupStudioOnce() {
  if (studioReady) return;
  studioReady = true;
  setupTimeline();
  setupTools();
  setupSelectionInputs();
  const audio = $("#st-audio");
  $("#st-play").addEventListener("click", () => audio.paused ? audio.play() : audio.pause());
  audio.addEventListener("play", () => { $("#st-play").textContent = "❚❚"; $("#audio").pause(); });
  audio.addEventListener("pause", () => { $("#st-play").textContent = "▶"; });
  audio.addEventListener("timeupdate", () => {
    if (!studio.song) return;
    studio.playhead = audio.currentTime;
    $("#st-cur").textContent = fmtT(audio.currentTime);
    drawStudio();
  });
  $("#st-close").addEventListener("click", closeStudio);
  $("#st-undo").addEventListener("click", undoStudio);
  $("#st-redo").addEventListener("click", redoStudio);
  $("#st-reset").addEventListener("click", async () => {
    if (!confirm("Remove every edit and mix change for this song?")) return;
    try {
      studio.undo = []; studio.redo = [];
      applyState(await api(`/api/songs/${studio.song.id}/studio/reset`, { method: "POST" }));
      setStatus("Back to the original.");
    } catch (e) { setStatus(e.message, "err"); }
  });
  $("#st-source").addEventListener("change", ev => {
    const source = ev.target.value;
    change(doc => {
      doc.source = source;
      doc.tracks = [];
      doc.edits.forEach(e => delete e.tracks);
    }, { now: true });
  });
  $("#st-session").addEventListener("click", () => setStatus("Preparing the SoundCraft session… the download starts when it's ready.", "busy"));
  $("#st-save").addEventListener("click", async () => {
    const title = prompt("Title for the new song", `${studio.song.title} (edited)`);
    if (title === null) return;
    try {
      const song = await api(`/api/songs/${studio.song.id}/studio/save`, { method: "POST", body: { doc: studio.doc, title } });
      state.songs.unshift(song);
      renderSongs(); poll();
      setStatus(`Saving “${song.title}” to your library…`);
    } catch (e) { setStatus(e.message, "err"); }
  });
  document.addEventListener("keydown", ev => {
    if (!studio.song || ["INPUT", "SELECT", "TEXTAREA"].includes(ev.target.tagName)) return;
    const mod = ev.ctrlKey || ev.metaKey;
    if (mod && ev.key.toLowerCase() === "z") { ev.preventDefault(); ev.shiftKey ? redoStudio() : undoStudio(); }
    else if (ev.key === " ") { ev.preventDefault(); $("#st-play").click(); }
    else if (ev.key === "Escape") closeStudio();
  });
}

window.openStudio = openStudio;
