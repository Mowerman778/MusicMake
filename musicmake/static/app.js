"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const STYLE_IDEAS = ["pop", "lofi", "rock", "folk", "jazz", "house", "synthwave", "hip hop",
  "ambient", "cinematic", "r&b", "funk", "piano", "acoustic", "chiptune", "upbeat", "mellow", "dark", "dreamy"];
const KEYS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];

const state = {
  songs: [],
  tab: "quick",
  current: null,      // id of the song in the player
  openMenu: null,
  drawer: null,       // id of the song in the drawer
  pollTimer: null,
};

// ------------------------------------------------------------------ api
async function api(path, opts = {}) {
  const init = { ...opts, headers: { ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) } };
  if (init.body && typeof init.body !== "string" && !(init.body instanceof FormData)) init.body = JSON.stringify(init.body);
  const r = await fetch(path, init);
  if (r.status === 204) return null;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    let msg = data.detail;
    if (Array.isArray(msg)) msg = msg.map(d => d.msg).join("; ");
    throw new Error(msg || `Request failed (${r.status})`);
  }
  return data;
}

// ------------------------------------------------------------------ utils
const fmt = s => {
  s = Math.max(0, Math.round(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const splitList = v => v.split(",").map(x => x.trim()).filter(Boolean);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function drawWave(canvas, peaks, progress = 0) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  if (!peaks || !peaks.length) return;
  const bars = Math.min(peaks.length, Math.floor(w / 3));
  const step = peaks.length / bars;
  const bw = w / bars;
  const off = cssVar("--wave"), on = cssVar("--wave-on");
  for (let i = 0; i < bars; i++) {
    const v = peaks[Math.floor(i * step)] || 0;
    const bh = Math.max(2, v * (h - 2));
    ctx.fillStyle = (i / bars) < progress ? on : off;
    ctx.fillRect(i * bw, (h - bh) / 2, Math.max(1, bw - 1), bh);
  }
}

// ------------------------------------------------------------------ create form
function setupForm() {
  $$(".tab").forEach(t => t.addEventListener("click", () => {
    state.tab = t.dataset.tab;
    $$(".tab").forEach(x => { x.classList.toggle("active", x === t); x.setAttribute("aria-selected", x === t); });
    $$(".tabpane").forEach(p => p.classList.toggle("hidden", p.dataset.pane !== state.tab));
  }));

  const keySel = $("#key");
  for (const k of KEYS) for (const m of ["major", "minor"]) keySel.add(new Option(`${k} ${m}`, `${k} ${m}`));

  const chips = $("#style-chips");
  for (const s of STYLE_IDEAS) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.textContent = s;
    b.addEventListener("click", () => {
      const cur = splitList($("#styles").value);
      if (!cur.includes(s)) cur.push(s);
      $("#styles").value = cur.join(", ");
    });
    chips.append(b);
  }

  const dur = $("#duration"), durOut = $("#dur-out");
  dur.addEventListener("input", () => durOut.textContent = fmt(+dur.value));
  const adv = $("#adventurous");
  adv.addEventListener("input", () => $("#adv-out").textContent = adv.value + "%");

  $("#lyrics-help-btn").addEventListener("click", () => $("#lyrics-help").classList.toggle("hidden"));
  $("#lh-go").addEventListener("click", writeLyrics);
  $("#create-form").addEventListener("submit", e => { e.preventDefault(); makeSong(); });
  $("#upload-file").addEventListener("change", uploadFile);
}

function collectRequest() {
  const body = {
    instrumental: $("#instrumental").checked,
    duration: +$("#duration").value,
    takes: +$("#takes").value,
    engine: $("#engine").value || null,
  };
  if (state.tab === "quick") {
    body.prompt = $("#prompt").value.trim();
  } else {
    Object.assign(body, {
      title: $("#title").value.trim(),
      lyrics: $("#lyrics").value,
      styles: splitList($("#styles").value),
      exclude: splitList($("#exclude").value),
      key: $("#key").value || null,
      adventurous: +$("#adventurous").value / 100,
    });
    if ($("#bpm").value) body.bpm = +$("#bpm").value;
    if ($("#seed").value !== "") body.seed = +$("#seed").value;
  }
  return body;
}

async function makeSong() {
  const btn = $("#make-btn"), err = $("#create-error");
  err.textContent = "";
  btn.disabled = true;
  try {
    const songs = await api("/api/songs", { method: "POST", body: collectRequest() });
    state.songs = [...songs, ...state.songs];
    renderSongs();
    poll();
  } catch (e) {
    err.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
}

async function writeLyrics() {
  const status = $("#lh-status"), btn = $("#lh-go");
  btn.disabled = true; status.textContent = "Writing…";
  try {
    const r = await api("/api/lyrics", { method: "POST", body: {
      topic: $("#lh-topic").value, mood: $("#lh-mood").value, length: $("#lh-length").value,
      styles: $("#styles").value, existing: $("#lyrics").value,
    } });
    $("#lyrics").value = r.lyrics;
    if (r.title && !$("#title").value) $("#title").value = r.title;
    status.textContent = r.source === "claude" ? "Written by Claude. Edit freely." :
      (r.note || "A template to fill in (set ANTHROPIC_API_KEY to have Claude write lyrics).");
  } catch (e) {
    status.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
}

async function uploadFile(e) {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  fd.append("title", f.name.replace(/\.[^.]+$/, ""));
  try {
    const song = await api("/api/uploads", { method: "POST", body: fd });
    state.songs.unshift(song);
    renderSongs();
  } catch (err) {
    alert(err.message);
  }
  e.target.value = "";
}

// ------------------------------------------------------------------ library
function songSub(s) {
  const r = s.request || {}, m = s.meta || {};
  const bits = [];
  if (s.kind === "upload") bits.push("uploaded");
  if (s.kind === "extend") bits.push("extended");
  if (s.kind === "remix") bits.push("remix");
  const styles = (r.styles || []).join(", ") || r.prompt || "";
  if (styles) bits.push(styles);
  if (m.bpm) bits.push(`${m.bpm} BPM`);
  if (m.key) bits.push(m.key);
  if (s.duration) bits.push(fmt(s.duration));
  return bits.join(" · ");
}

function renderSongs() {
  const list = $("#songs");
  const q = $("#search").value.trim().toLowerCase();
  const liked = $("#only-liked").checked;
  const songs = state.songs.filter(s => (!liked || s.liked) &&
    (!q || (s.title + " " + (s.lyrics || "") + " " + JSON.stringify(s.request || {})).toLowerCase().includes(q)));
  $("#empty").classList.toggle("hidden", songs.length > 0);
  list.innerHTML = "";
  for (const s of songs) {
    const li = document.createElement("li");
    li.className = "song" + (s.id === state.current ? " playing" : "");
    li.dataset.id = s.id;
    const busy = s.status === "queued" || s.status === "running";
    const isCur = s.id === state.current && !$("#audio").paused;
    li.innerHTML = `
      <button class="icon big play" ${s.status !== "done" ? "disabled" : ""} aria-label="${isCur ? "Pause" : "Play"} ${esc(s.title)}">${isCur ? "❚❚" : "▶"}</button>
      <div class="info">
        <div class="title">${esc(s.title)}${s.status === "failed" ? '<span class="badge fail">failed</span>' : ""}${busy ? `<span class="badge">${s.status === "queued" ? "queued" : Math.round(s.progress * 100) + "%"}</span>` : ""}</div>
        <div class="sub">${busy ? esc(s.message || "Waiting…") : s.status === "failed" ? esc(s.error || "") : esc(songSub(s))}</div>
        ${busy ? `<div class="bar"><i style="width:${Math.round(s.progress * 100)}%"></i></div>` : `<canvas></canvas>`}
      </div>
      <div class="actions">
        <button class="icon like ${s.liked ? "liked" : ""}" aria-label="Favourite" aria-pressed="${s.liked}">${s.liked ? "♥" : "♡"}</button>
        <div class="menu"><button class="icon more" aria-label="More actions" aria-haspopup="true">⋯</button></div>
      </div>`;
    list.append(li);
    const c = $("canvas", li);
    if (c) drawWave(c, s.peaks, s.id === state.current ? playProgress() : 0);
    $(".play", li).addEventListener("click", () => togglePlay(s.id));
    $(".info", li).addEventListener("click", () => openDrawer(s.id));
    $(".like", li).addEventListener("click", () => patchSong(s.id, { liked: !s.liked }));
    $(".more", li).addEventListener("click", ev => { ev.stopPropagation(); openMenu(li, s); });
  }
}

function openMenu(li, s) {
  closeMenu();
  const ready = s.status === "done";
  const items = [
    ["Details & lyrics", () => openDrawer(s.id), true],
    ["Extend…", () => extendDialog(s), ready],
    ["Remix…", () => remixDialog(s), ready],
    [s.stems && s.stems.length ? "Stems" : "Split into stems", () => stems(s), ready],
    ["Download WAV", () => download(s, "wav"), ready],
    ["Download MP3", () => download(s, "mp3"), ready],
    ["Use these settings", () => reuseSettings(s), !!s.request && s.kind !== "upload"],
    ["Rename", () => rename(s), true],
    ["Delete", () => del(s), s.status !== "queued" && s.status !== "running", "danger"],
  ];
  const box = document.createElement("div");
  box.className = "menu-list"; box.setAttribute("role", "menu");
  for (const [label, fn, ok, cls] of items) {
    if (!ok) continue;
    const b = document.createElement("button");
    b.textContent = label; b.setAttribute("role", "menuitem");
    if (cls) b.className = cls;
    b.addEventListener("click", ev => { ev.stopPropagation(); closeMenu(); fn(); });
    box.append(b);
  }
  $(".menu", li).append(box);
  state.openMenu = box;
}
function closeMenu() { state.openMenu?.remove(); state.openMenu = null; }
document.addEventListener("click", closeMenu);
document.addEventListener("keydown", e => { if (e.key === "Escape") { closeMenu(); closeDrawer(); } });

async function patchSong(id, body) {
  const s = await api(`/api/songs/${id}`, { method: "PATCH", body });
  replaceSong(s);
}
function replaceSong(s) {
  const i = state.songs.findIndex(x => x.id === s.id);
  if (i >= 0) state.songs[i] = s; else state.songs.unshift(s);
  renderSongs();
  if (state.drawer === s.id) renderDrawer();
}

function rename(s) {
  const t = prompt("New title", s.title);
  if (t && t.trim()) patchSong(s.id, { title: t.trim() });
}

async function del(s) {
  if (!confirm(`Delete “${s.title}”? This can't be undone.`)) return;
  try {
    await api(`/api/songs/${s.id}`, { method: "DELETE" });
    state.songs = state.songs.filter(x => x.id !== s.id);
    if (state.current === s.id) { $("#audio").pause(); state.current = null; updatePlayer(); }
    if (state.drawer === s.id) closeDrawer();
    renderSongs();
  } catch (e) { alert(e.message); }
}

function download(s, format) {
  const a = document.createElement("a");
  a.href = `/api/songs/${s.id}/audio?format=${format}&download=true`;
  a.download = "";
  document.body.append(a); a.click(); a.remove();
}

async function stems(s) {
  if (s.stems && s.stems.length) { openDrawer(s.id); return; }
  try {
    replaceSong(await api(`/api/songs/${s.id}/stems`, { method: "POST" }));
    openDrawer(s.id);
    poll();
  } catch (e) { alert(e.message); }
}

function extendDialog(s) {
  const dlg = $("#extend-dlg");
  const r = $("#ext-seconds");
  r.oninput = () => $("#ext-out").textContent = r.value;
  $("#ext-lyrics").value = "";
  dlg.onclose = async () => {
    if (dlg.returnValue !== "ok") return;
    try {
      const song = await api(`/api/songs/${s.id}/extend`, { method: "POST", body: { seconds: +r.value, lyrics: $("#ext-lyrics").value } });
      state.songs.unshift(song); renderSongs(); poll();
    } catch (e) { alert(e.message); }
  };
  dlg.showModal();
}

function remixDialog(s) {
  const dlg = $("#remix-dlg");
  const r = $("#rmx-strength");
  r.oninput = () => $("#rmx-out").textContent = r.value + "%";
  $("#rmx-styles").value = (s.request?.styles || []).join(", ");
  dlg.onclose = async () => {
    if (dlg.returnValue !== "ok") return;
    try {
      const song = await api(`/api/songs/${s.id}/remix`, { method: "POST", body: { styles: splitList($("#rmx-styles").value), strength: +r.value / 100 } });
      state.songs.unshift(song); renderSongs(); poll();
    } catch (e) { alert(e.message); }
  };
  dlg.showModal();
}

function reuseSettings(s) {
  const r = s.request || {};
  $$(".tab").find(t => t.dataset.tab === "detailed").click();
  $("#prompt").value = r.prompt || "";
  $("#title").value = "";
  $("#lyrics").value = r.lyrics || "";
  $("#styles").value = (r.styles || []).join(", ") || r.prompt || "";
  $("#exclude").value = (r.exclude || []).join(", ");
  $("#bpm").value = s.meta?.bpm || r.bpm || "";
  $("#key").value = r.key || "";
  $("#seed").value = s.meta?.seed ?? "";
  $("#instrumental").checked = !!r.instrumental;
  $("#duration").value = r.duration || 120; $("#duration").dispatchEvent(new Event("input"));
  $("#adventurous").value = Math.round((r.adventurous ?? 0.5) * 100); $("#adventurous").dispatchEvent(new Event("input"));
  $("#create-form").scrollIntoView({ behavior: "smooth" });
}

// ------------------------------------------------------------------ drawer
function openDrawer(id) { state.drawer = id; renderDrawer(); $("#drawer").classList.remove("hidden"); }
function closeDrawer() { state.drawer = null; $("#drawer").classList.add("hidden"); }
$("#drawer-close").addEventListener("click", closeDrawer);

function renderDrawer() {
  const s = state.songs.find(x => x.id === state.drawer);
  if (!s) { closeDrawer(); return; }
  const m = s.meta || {}, r = s.request || {};
  const rows = [
    ["Engine", m.engine || s.engine], ["Styles", (r.styles || []).join(", ") || r.prompt],
    ["Tempo", m.bpm && `${m.bpm} BPM`], ["Key", m.key], ["Length", s.duration && fmt(s.duration)],
    ["Seed", m.seed], ["Made", new Date(s.created_at * 1000).toLocaleString()],
  ].filter(([, v]) => v !== undefined && v !== null && v !== "");
  const parent = s.parent_id && state.songs.find(x => x.id === s.parent_id);
  let stemsHtml = "";
  if (s.stems_status === "running") stemsHtml = `<p class="muted">Splitting into stems…</p>`;
  else if (s.stems && s.stems.length) stemsHtml = `<ul class="stems">${s.stems.map(n => `
      <li><button class="icon" data-stem="${esc(n)}" aria-label="Play ${esc(n)}">▶</button><span>${esc(n)}</span>
      <a class="btn small" href="/api/songs/${s.id}/stems/${encodeURIComponent(n)}?download=true">WAV</a></li>`).join("")}</ul>`;
  else if (s.status === "done") stemsHtml = `<button class="btn small" id="dr-split">Split into stems</button>`;
  $("#drawer-body").innerHTML = `
    <h2>${esc(s.title)}</h2>
    ${parent ? `<p class="muted small">From <a href="#" id="dr-parent">${esc(parent.title)}</a></p>` : ""}
    ${s.status === "failed" ? `<p class="error">${esc(s.error)}</p>` : ""}
    <dl class="meta">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    <h3>Lyrics</h3>
    ${s.lyrics ? `<div class="lyrics-view">${esc(s.lyrics)}</div>` : `<p class="muted">${r.instrumental ? "Instrumental" : "No lyrics"}</p>`}
    <h3 style="margin-top:16px">Stems</h3>
    ${stemsHtml || `<p class="muted">Available when the song is ready.</p>`}`;
  $("#dr-parent")?.addEventListener("click", e => { e.preventDefault(); openDrawer(parent.id); });
  $("#dr-split")?.addEventListener("click", () => stems(s));
  $$("[data-stem]").forEach(b => b.addEventListener("click", () => playUrl(`/api/songs/${s.id}/stems/${encodeURIComponent(b.dataset.stem)}`, `${s.title} – ${b.dataset.stem}`, s.id, null)));
}

// ------------------------------------------------------------------ player
const audio = $("#audio");
audio.volume = 0.85;
$("#pl-vol").addEventListener("input", e => audio.volume = e.target.value / 100);

function playable() { return state.songs.filter(s => s.status === "done"); }
function playProgress() { return audio.duration ? audio.currentTime / audio.duration : 0; }

function playUrl(url, title, id, peaks) {
  state.current = id;
  state.currentPeaks = peaks;
  audio.src = url;
  audio.play();
  $("#pl-title").textContent = title;
  renderSongs();
}
function togglePlay(id) {
  if (state.current === id && audio.src) { audio.paused ? audio.play() : audio.pause(); return; }
  const s = state.songs.find(x => x.id === id);
  playUrl(`/api/songs/${id}/audio`, s.title, id, s.peaks);
}
function skip(dir) {
  const list = playable();
  if (!list.length) return;
  const i = list.findIndex(s => s.id === state.current);
  const next = list[(i + dir + list.length) % list.length];
  togglePlay(next.id);
}
function updatePlayer() {
  $("#pl-play").textContent = audio.paused ? "▶" : "❚❚";
  $("#pl-play").setAttribute("aria-label", audio.paused ? "Play" : "Pause");
  $("#pl-cur").textContent = fmt(audio.currentTime);
  $("#pl-dur").textContent = fmt(audio.duration);
  drawWave($("#pl-wave"), state.currentPeaks || new Array(120).fill(0.25), playProgress());
  const row = state.current && $(`.song[data-id="${state.current}"] canvas`);
  if (row) drawWave(row, state.songs.find(s => s.id === state.current)?.peaks, playProgress());
}
$("#pl-play").addEventListener("click", () => {
  if (!audio.src) { const first = playable()[0]; if (first) togglePlay(first.id); return; }
  audio.paused ? audio.play() : audio.pause();
});
$("#pl-prev").addEventListener("click", () => skip(-1));
$("#pl-next").addEventListener("click", () => skip(1));
$("#pl-wave").addEventListener("click", e => {
  if (!audio.duration) return;
  const r = e.currentTarget.getBoundingClientRect();
  audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
});
audio.addEventListener("timeupdate", updatePlayer);
audio.addEventListener("play", () => { updatePlayer(); renderSongs(); });
audio.addEventListener("pause", () => { updatePlayer(); renderSongs(); });
audio.addEventListener("loadedmetadata", updatePlayer);
audio.addEventListener("ended", () => skip(1));
window.addEventListener("resize", () => { renderSongs(); updatePlayer(); });

// ------------------------------------------------------------------ polling & boot
async function refresh() {
  state.songs = await api("/api/songs");
  renderSongs();
  if (state.drawer) renderDrawer();
}
function busy() { return state.songs.some(s => s.status === "queued" || s.status === "running" || s.stems_status === "running"); }
function poll() {
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(async () => {
    try { await refresh(); } catch { /* server restarting */ }
    if (busy()) poll();
  }, 1500);
}

async function boot() {
  setupForm();
  $("#search").addEventListener("input", renderSongs);
  $("#only-liked").addEventListener("change", renderSongs);
  try {
    const h = await api("/api/health");
    const sel = $("#engine");
    sel.add(new Option("Auto", ""));
    for (const e of h.engines) sel.add(new Option(`${e.label}${e.available ? "" : " (offline)"}`, e.name));
    const ace = h.engines.find(e => e.name === "acestep");
    $("#engine-note").textContent = ace?.available ? "ACE-Step connected" : "Sketch mode: start ACE-Step for real vocals";
  } catch { /* ignore */ }
  await refresh();
  if (busy()) poll();
  updatePlayer();
}
boot();
