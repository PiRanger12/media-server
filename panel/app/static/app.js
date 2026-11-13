"use strict";

const state = { lib: "videos", path: "", entries: [] };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const q = (o) => new URLSearchParams(o).toString();

const VIDEO_PLAY = [".mp4", ".webm", ".m4v", ".mov"];
const AUDIO_EXT = [".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav", ".wma", ".aiff"];
const VIDEO_EXT = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv", ".ts"];

// ── utilidades ─────────────────────────────────────────────
function fmtSize(b) {
  if (b == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b.toFixed(i ? 1 : 0)} ${u[i]}`;
}
const fmtDate = (t) => new Date(t * 1000).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
function fmtDur(s) {
  if (!s) return "—";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : m) + ":" + String(x).padStart(2, "0");
}
function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4500);
}

async function api(url, opts = {}) {
  const r = await fetch(url, {
    ...opts,
    headers: opts.body && typeof opts.body === "string" ? { "Content-Type": "application/json" } : {},
  });
  if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const data = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) throw new Error(data?.detail || `Error ${r.status}`);
  return data;
}
const post = (url, body, method = "POST") => api(url, { method, body: JSON.stringify(body) });

// ── navegación ─────────────────────────────────────────────
async function load(path = state.path) {
  try {
    const data = await api(`/api/${state.lib}/list?${q({ path })}`);
    state.path = data.path === "." ? "" : data.path;
    state.entries = data.entries;
    render();
  } catch (e) {
    if (e.message !== "auth") toast(e.message, "err");
  }
}

function renderCrumbs() {
  const parts = state.path ? state.path.split("/") : [];
  const root = state.lib === "videos" ? "Videos" : "Música";
  let html = `<button data-path="">${root}</button>`;
  parts.forEach((p, i) => {
    html += `<span class="muted">/</span><button data-path="${esc(parts.slice(0, i + 1).join("/"))}">${esc(p)}</button>`;
  });
  $("#crumbs").innerHTML = html;
}

function iconFor(e) {
  if (e.type === "dir") return "📁";
  if (VIDEO_EXT.includes(e.ext)) return `<img loading="lazy" src="/api/videos/thumb?${q({ path: e.path })}" onerror="this.replaceWith('🎞️')">`;
  if (AUDIO_EXT.includes(e.ext)) return "🎵";
  if ([".jpg", ".jpeg", ".png", ".webp"].includes(e.ext)) return "🖼️";
  return "📄";
}

function render() {
  renderCrumbs();
  const filter = $("#search").value.trim().toLowerCase();
  const list = state.entries.filter((e) => !filter || e.name.toLowerCase().includes(filter));
  $("#empty").hidden = list.length > 0;
  $("#rows").innerHTML = list.map((e) => `
    <tr data-path="${esc(e.path)}" data-type="${e.type}" data-ext="${esc(e.ext)}">
      <td><div class="name" data-act="open"><div class="icon">${iconFor(e)}</div><span class="label">${esc(e.name)}</span></div></td>
      <td class="hide-sm muted">${e.type === "dir" ? "—" : fmtSize(e.size)}</td>
      <td class="hide-sm muted">${fmtDate(e.modified)}</td>
      <td><div class="actions">
        ${e.type === "file" ? `<button data-act="info" title="Información">ℹ️</button>` : ""}
        ${e.type === "file" && state.lib === "music" && AUDIO_EXT.includes(e.ext) ? `<button data-act="tags" title="Editar etiquetas">🏷️</button>` : ""}
        <button data-act="rename" title="Renombrar">✏️</button>
        <button data-act="move" title="Mover">📦</button>
        <button data-act="delete" title="Eliminar">🗑️</button>
      </div></td>
    </tr>`).join("");
}

// ── diálogos ───────────────────────────────────────────────
function dialog(html, onSubmit) {
  const d = $("#dlg");
  d.innerHTML = html;
  d.showModal();
  d.querySelector("[data-close]")?.addEventListener("click", () => d.close());
  const form = d.querySelector("form");
  if (form && onSubmit) {
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const btn = form.querySelector("[type=submit]");
      btn.disabled = true;
      try { await onSubmit(new FormData(form)); d.close(); }
      catch (e) { toast(e.message, "err"); }
      finally { btn.disabled = false; }
    });
  }
  d.addEventListener("close", () => d.querySelectorAll("video,audio").forEach((m) => m.pause()), { once: true });
  return d;
}

const cancelBtn = `<button type="button" class="btn" data-close>Cancelar</button>`;

function newFolder() {
  dialog(`<h3>Nueva carpeta</h3><form class="form">
      <label>Nombre<input name="name" required autofocus placeholder="${state.lib === "music" ? "Artista o Álbum" : "Película (2024)"}"></label>
      <div class="dialog-actions">${cancelBtn}<button class="btn primary" type="submit">Crear</button></div></form>`,
    async (f) => { await post(`/api/${state.lib}/folder`, { parent: state.path, name: f.get("name") }); toast("Carpeta creada", "ok"); load(); });
}

function renameItem(path) {
  const current = path.split("/").pop();
  const d = dialog(`<h3>Renombrar</h3><form class="form">
      <label>Nuevo nombre<input name="name" required value="${esc(current)}"></label>
      <div class="dialog-actions">${cancelBtn}<button class="btn primary" type="submit">Guardar</button></div></form>`,
    async (f) => { await post(`/api/${state.lib}/rename`, { path, new_name: f.get("name") }); toast("Renombrado", "ok"); load(); });
  const inp = d.querySelector("input");
  const dot = current.lastIndexOf(".");
  inp.focus();
  inp.setSelectionRange(0, dot > 0 ? dot : current.length);
}

async function moveItem(path) {
  const { folders } = await api(`/api/${state.lib}/folders`);
  const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
  const opts = folders
    .filter((f) => f !== parent && f !== path && !f.startsWith(path + "/"))
    .map((f) => `<option value="${esc(f)}">${esc(f || "/ (raíz)")}</option>`).join("");
  dialog(`<h3>Mover “${esc(path.split("/").pop())}”</h3><form class="form">
      <label>Carpeta destino<select name="dest">${opts}</select></label>
      <div class="dialog-actions">${cancelBtn}<button class="btn primary" type="submit">Mover</button></div></form>`,
    async (f) => { await post(`/api/${state.lib}/move`, { path, dest: f.get("dest") }); toast("Movido", "ok"); load(); });
}

function deleteItem(path, type) {
  dialog(`<h3>¿Eliminar?</h3><form class="form">
      <p>Se borrará <b>${esc(path.split("/").pop())}</b>${type === "dir" ? " <b>y todo su contenido</b>" : ""}. No se puede deshacer.</p>
      <div class="dialog-actions">${cancelBtn}<button class="btn primary" style="background:var(--bad);border-color:var(--bad)" type="submit">Eliminar</button></div></form>`,
    async () => { await api(`/api/${state.lib}/item?${q({ path })}`, { method: "DELETE" }); toast("Eliminado", "ok"); load(); });
}

async function showInfo(path, ext) {
  const info = await api(`/api/${state.lib}/info?${q({ path })}`);
  const src = `/api/${state.lib}/stream?${q({ path })}`;
  let player = "", rows = "";
  if (info.kind === "audio") {
    player = `<audio controls src="${src}"></audio>`;
    const t = info.tags;
    rows = [["Título", t.title], ["Artista", t.artist], ["Álbum", t.album], ["Artista del álbum", t.albumartist],
      ["Género", t.genre], ["Año", t.date], ["Pista", t.tracknumber], ["Duración", fmtDur(info.duration)],
      ["Bitrate", info.bitrate ? `${Math.round(info.bitrate / 1000)} kbps` : "—"], ["Formato", info.format]];
  } else {
    if (VIDEO_PLAY.includes(ext)) player = `<video controls preload="metadata" src="${src}"></video>`;
    rows = [["Duración", fmtDur(info.duration)], ["Resolución", info.resolution], ["Códec de video", info.video_codec],
      ["Contenedor", info.container], ["Tamaño", fmtSize(info.size)],
      ["Audio", info.audio_tracks.map((a) => `${a.codec}${a.language ? ` (${a.language})` : ""}`).join(", ") || "—"],
      ["Subtítulos", info.subtitles.join(", ") || "—"]];
    if (!player) rows.push(["Vista previa", "Este formato no se reproduce en el navegador; ábrelo en Jellyfin."]);
  }
  dialog(`<h3>${esc(path.split("/").pop())}</h3>${player}
    <dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v || "—")}</dd>`).join("")}</dl>
    <div class="dialog-actions"><button class="btn" data-close>Cerrar</button></div>`);
}

async function editTags(path) {
  const { tags } = await api(`/api/music/info?${q({ path })}`);
  const field = (k, label) => `<label>${label}<input name="${k}" value="${esc(tags[k])}"></label>`;
  dialog(`<h3>Etiquetas · ${esc(path.split("/").pop())}</h3><form class="form">
      ${field("title", "Título")}
      <div class="grid2">${field("artist", "Artista")}${field("albumartist", "Artista del álbum")}</div>
      ${field("album", "Álbum")}
      <div class="grid2">${field("genre", "Género")}${field("date", "Año")}</div>
      <div class="grid2">${field("tracknumber", "Núm. de pista")}${field("discnumber", "Núm. de disco")}</div>
      <div class="dialog-actions">${cancelBtn}<button class="btn primary" type="submit">Guardar</button></div></form>`,
    async (f) => { await post(`/api/music/tags`, { path, tags: Object.fromEntries(f) }, "PUT"); toast("Etiquetas guardadas", "ok"); });
}

// ── subida ─────────────────────────────────────────────────
function uploadFiles(files) {
  const lib = state.lib, path = state.path;
  for (const file of files) {
    const el = document.createElement("div");
    el.className = "upload";
    el.innerHTML = `<div class="row"><span>${esc(file.name)}</span><span class="muted pct">0 %</span></div><div class="bar"><div style="width:0"></div></div>`;
    $("#uploads").append(el);
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `/api/${lib}/upload?${q({ path, name: file.name })}`);
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const p = Math.round((e.loaded / e.total) * 100);
      el.querySelector(".bar > div").style.width = p + "%";
      el.querySelector(".pct").textContent = `${p} % · ${fmtSize(e.loaded)} / ${fmtSize(e.total)}`;
    };
    xhr.onload = () => {
      if (xhr.status === 200) {
        el.remove();
        toast(`Subido: ${file.name}`, "ok");
        if (state.lib === lib && state.path === path) load();
      } else {
        el.classList.add("error");
        let msg = `Error ${xhr.status}`;
        try { msg = JSON.parse(xhr.responseText).detail; } catch {}
        el.querySelector(".pct").textContent = msg;
        setTimeout(() => el.remove(), 8000);
      }
    };
    xhr.onerror = () => { el.classList.add("error"); el.querySelector(".pct").textContent = "Error de red"; };
    xhr.send(file);
  }
}

// ── barra lateral ──────────────────────────────────────────
async function refreshSidebar() {
  try {
    const s = await api("/api/status");
    const host = location.hostname;
    const card = (name, lib, x) => `
      <div class="service">
        <div class="row"><b><span class="dot ${x.online ? "on" : "off"}"></span>${name}</b>
          <a href="http://${host}:${x.port}" target="_blank">Abrir ↗</a></div>
        <small>${x.online ? "En línea" : "Sin conexión"}${x.version ? " · v" + esc(x.version) : ""}${x.configured ? "" : " · falta configurar"}</small>
        ${x.last_scan.at ? `<small>Último escaneo: ${new Date(x.last_scan.at * 1000).toLocaleTimeString("es-MX")} ${x.last_scan.ok ? "✓" : "⚠ " + esc(x.last_scan.detail)}</small>` : ""}
      </div>`;
    $("#services").innerHTML = card("Jellyfin", "videos", s.videos) + card("Navidrome", "music", s.music);
  } catch {}
  try {
    const st = await api("/api/stats");
    const pct = (st.disk.used / st.disk.total) * 100;
    $("#disk").innerHTML = `
      <div>Disco: ${fmtSize(st.disk.free)} libres de ${fmtSize(st.disk.total)}</div>
      <div class="bar"><div style="width:${pct.toFixed(1)}%"></div></div>
      <div>🎞️ ${st.libraries.videos.files} archivos · ${fmtSize(st.libraries.videos.size)}</div>
      <div>🎵 ${st.libraries.music.files} archivos · ${fmtSize(st.libraries.music.size)}</div>`;
  } catch {}
}

// ── eventos ────────────────────────────────────────────────
document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("active", x === b));
  state.lib = b.dataset.lib;
  $("#search").value = "";
  load("");
}));
$("#crumbs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) load(b.dataset.path); });
$("#search").addEventListener("input", render);
$("#btn-folder").addEventListener("click", newFolder);
$("#btn-upload").addEventListener("click", () => $("#file-input").click());
$("#file-input").addEventListener("change", (e) => { uploadFiles(e.target.files); e.target.value = ""; });
$("#btn-scan").addEventListener("click", async () => {
  try {
    const r = await api(`/api/${state.lib}/scan`, { method: "POST" });
    toast(r.detail, r.ok ? "ok" : "err");
    refreshSidebar();
  } catch (e) { toast(e.message, "err"); }
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); location.href = "/login"; });

$("#rows").addEventListener("click", (e) => {
  const act = e.target.closest("[data-act]")?.dataset.act;
  const tr = e.target.closest("tr");
  if (!act || !tr) return;
  const { path, type, ext } = tr.dataset;
  const run = {
    open: () => (type === "dir" ? load(path) : showInfo(path, ext)),
    info: () => showInfo(path, ext),
    tags: () => editTags(path),
    rename: () => renameItem(path),
    move: () => moveItem(path),
    delete: () => deleteItem(path, type),
  }[act];
  Promise.resolve(run?.()).catch((err) => toast(err.message, "err"));
});

const drop = $("#drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); if (ev === "drop" || !drop.contains(e.relatedTarget)) drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));

load("");
refreshSidebar();
setInterval(refreshSidebar, 30000);
