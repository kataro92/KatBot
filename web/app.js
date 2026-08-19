const stateEl = document.getElementById("state");
const tempEl = document.getElementById("temp");
const humidityEl = document.getElementById("humidity");
const sessionEl = document.getElementById("session");
const devicePill = document.getElementById("devicePill");
const ollamaPill = document.getElementById("ollamaPill");
const eventLog = document.getElementById("eventLog");
const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const listenBar = document.getElementById("listenBar");
const listenProgress = document.getElementById("listenProgress");
const chartCanvas = document.getElementById("deviceChart");
const chartCtx = chartCanvas.getContext("2d");
const chartRanges = document.getElementById("chartRanges");
const customRange = document.getElementById("customRange");
const chartFromEl = document.getElementById("chartFrom");
const chartToEl = document.getElementById("chartTo");
const chartApply = document.getElementById("chartApply");
const chartWindowLabel = document.getElementById("chartWindowLabel");

let listenTimer = null;
let listenEndsAt = 0;
let deviceOnline = false;
let lastTemp = null;
let lastHum = null;

const RANGE_MS = {
  "1m": 60 * 1000,
  "15m": 15 * 60 * 1000,
  "1h": 60 * 60 * 1000,
  "3h": 3 * 60 * 60 * 1000,
  "12h": 12 * 60 * 60 * 1000,
  "1d": 24 * 60 * 60 * 1000,
};
const RANGE_LABEL = {
  "1m": "1 phút",
  "15m": "15 phút",
  "1h": "1 tiếng",
  "3h": "3 tiếng",
  "12h": "12 tiếng",
  "1d": "1 ngày",
  custom: "Tùy chọn",
};

let chartWindow = "15m";
let customFromMs = null;
let customToMs = null;
let chartFromMs = Date.now() - RANGE_MS["15m"];
let chartToMs = Date.now();
const history = []; // { t, temp, hum }

function formatClock(ts) {
  return new Date(ts).toLocaleTimeString();
}

function addLog(message, cls, ts) {
  const li = document.createElement("li");
  if (cls) li.className = cls;
  li.textContent = `${formatClock(ts || Date.now())}  ${message}`;
  eventLog.prepend(li);
  while (eventLog.children.length > 400) eventLog.lastChild.remove();
}

function addChat(role, text, audioId, ts) {
  const li = document.createElement("li");
  li.className = role;
  const label = document.createElement("span");
  label.className = "chat-text";
  const prefix = role === "user" ? "Bạn" : "Mèo";
  const when = ts ? ` (${formatClock(ts)})` : "";
  label.textContent = `${prefix}: ${text}${when}`;
  li.appendChild(label);
  if (role === "user" && audioId) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "play-clip";
    btn.title = "Nghe lại mic";
    btn.setAttribute("aria-label", "Nghe lại mic");
    setClipIcon(btn, false);
    btn.addEventListener("click", () => toggleClip(btn, audioId));
    li.appendChild(btn);
  }
  chatLog.appendChild(li);
  scrollChatToEnd();
}

function scrollChatToEnd() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

let clipPlayer = null;
let clipPlayingBtn = null;

const ICON_PLAY =
  '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
const ICON_STOP =
  '<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><rect fill="currentColor" x="6" y="6" width="12" height="12" rx="2"/></svg>';

function setClipIcon(btn, playing) {
  btn.innerHTML = playing ? ICON_STOP : ICON_PLAY;
  btn.classList.toggle("playing", playing);
}

function resetClipButton(btn) {
  if (!btn) return;
  setClipIcon(btn, false);
}

function toggleClip(btn, audioId) {
  if (clipPlayer && clipPlayingBtn === btn && !clipPlayer.paused) {
    clipPlayer.pause();
    clipPlayer.currentTime = 0;
    resetClipButton(btn);
    return;
  }
  if (clipPlayer) {
    clipPlayer.pause();
    resetClipButton(clipPlayingBtn);
  }
  clipPlayer = new Audio(`/api/clips/${encodeURIComponent(audioId)}`);
  clipPlayingBtn = btn;
  setClipIcon(btn, true);
  clipPlayer.onended = () => resetClipButton(btn);
  clipPlayer.onerror = () => {
    addLog("Không phát được bản ghi mic", "err");
    resetClipButton(btn);
  };
  clipPlayer.play().catch((err) => {
    addLog(String(err), "err");
    resetClipButton(btn);
  });
}

function setDeviceOnline(online) {
  deviceOnline = !!online;
  devicePill.textContent = deviceOnline ? "ESP online" : "ESP offline";
  devicePill.classList.toggle("ok", deviceOnline);
  devicePill.classList.toggle("bad", !deviceOnline);
}

function setTemp(v) {
  if (v == null || Number.isNaN(Number(v))) return;
  lastTemp = Number(v);
  tempEl.textContent = `${lastTemp.toFixed(1)} °C`;
}

function setHum(v) {
  if (v == null || Number.isNaN(Number(v))) return;
  lastHum = Number(v);
  humidityEl.textContent = `${lastHum.toFixed(0)} %`;
}

function isLiveWindow() {
  if (chartWindow !== "custom") return true;
  return customToMs == null || customToMs >= Date.now() - 5000;
}

function pushPoint(t, temp, hum) {
  if (temp == null && hum == null) return;
  history.push({ t, temp, hum });
}

function applySnapshot(msg) {
  setDeviceOnline(!!msg.device_online);
  stateEl.textContent = msg.state || "offline";
  if (msg.temp != null) setTemp(msg.temp);
  if (msg.humidity != null) setHum(msg.humidity);
  sessionEl.textContent = msg.session_id ? `phiên ${msg.session_id}` : "phiên —";
}

function niceRange(min, max, fallbackMin, fallbackMax) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return { min: fallbackMin, max: fallbackMax };
  }
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.12;
  return { min: min - pad, max: max + pad };
}

function mapX(t, t0, t1, x0, x1) {
  if (t1 <= t0) return x1;
  return x0 + ((t - t0) / (t1 - t0)) * (x1 - x0);
}

function mapY(v, yMin, yMax, y0, y1) {
  if (yMax === yMin) return (y0 + y1) / 2;
  return y1 - ((v - yMin) / (yMax - yMin)) * (y1 - y0);
}

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function drawSeries(ctx, pts, key, yMin, yMax, x0, x1, y0, y1, t0, t1, stroke, fill, dash) {
  const usable = pts.filter((p) => p[key] != null);
  if (usable.length < 1) return;
  ctx.beginPath();
  usable.forEach((p, i) => {
    const x = mapX(p.t, t0, t1, x0, x1);
    const y = mapY(p[key], yMin, yMax, y0, y1);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  const last = usable[usable.length - 1];
  const lastX = mapX(last.t, t0, t1, x0, x1);
  const lastY = mapY(last[key], yMin, yMax, y0, y1);
  if (fill) {
    ctx.save();
    ctx.setLineDash([]);
    ctx.lineTo(lastX, y1);
    ctx.lineTo(mapX(usable[0].t, t0, t1, x0, x1), y1);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.restore();
    ctx.beginPath();
    usable.forEach((p, i) => {
      const x = mapX(p.t, t0, t1, x0, x1);
      const y = mapY(p[key], yMin, yMax, y0, y1);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
  }
  ctx.setLineDash(dash || []);
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2.2;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = stroke;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 3.4, 0, Math.PI * 2);
  ctx.fill();
}

function drawChart() {
  const wrap = chartCanvas.parentElement;
  const cssW = wrap.clientWidth - 16;
  const cssH = parseFloat(getComputedStyle(chartCanvas).height) || 240;
  const dpr = window.devicePixelRatio || 1;
  if (chartCanvas.width !== Math.floor(cssW * dpr) || chartCanvas.height !== Math.floor(cssH * dpr)) {
    chartCanvas.width = Math.max(1, Math.floor(cssW * dpr));
    chartCanvas.height = Math.max(1, Math.floor(cssH * dpr));
  }
  const ctx = chartCtx;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = cssW;
  const h = cssH;
  ctx.clearRect(0, 0, w, h);

  const pad = { l: 42, r: 42, t: 10, b: 24 };
  const x0 = pad.l;
  const x1 = w - pad.r;
  const y0 = pad.t;
  const y1 = h - pad.b;
  const t1 = isLiveWindow() ? Date.now() : chartToMs;
  const t0 = chartWindow === "custom" ? chartFromMs : t1 - (RANGE_MS[chartWindow] || RANGE_MS["15m"]);
  const tempColor = cssVar("--color-temp", "#0f766e");
  const humColor = cssVar("--color-hum", "#2563eb");
  const muted = cssVar("--color-muted-foreground", "#475569");

  ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.rect(x0, y0, x1 - x0, y1 - y0);
  ctx.stroke();

  const visible = history.filter((p) => p.t >= t0 && p.t <= t1);
  if (isLiveWindow() && visible.length && (lastTemp != null || lastHum != null)) {
    const last = visible[visible.length - 1];
    if (t1 - last.t > 800) visible.push({ t: t1, temp: lastTemp, hum: lastHum });
  }
  const temps = visible.map((p) => p.temp).filter((v) => v != null);
  const hums = visible.map((p) => p.hum).filter((v) => v != null);
  const tRange = niceRange(Math.min(...temps), Math.max(...temps), 15, 35);
  const hRange = niceRange(Math.min(...hums), Math.max(...hums), 30, 80);

  ctx.font = "600 11px Inter, \"Be Vietnam Pro\", system-ui, sans-serif";
  ctx.fillStyle = muted;
  for (let i = 0; i <= 4; i++) {
    const y = y0 + ((y1 - y0) * i) / 4;
    ctx.strokeStyle = "rgba(148, 163, 184, 0.22)";
    ctx.beginPath();
    ctx.moveTo(x0, y);
    ctx.lineTo(x1, y);
    ctx.stroke();
    const tv = tRange.max - ((tRange.max - tRange.min) * i) / 4;
    const hv = hRange.max - ((hRange.max - hRange.min) * i) / 4;
    ctx.textAlign = "right";
    ctx.fillStyle = tempColor;
    ctx.fillText(tv.toFixed(1), x0 - 6, y + 3);
    ctx.textAlign = "left";
    ctx.fillStyle = humColor;
    ctx.fillText(hv.toFixed(0), x1 + 6, y + 3);
  }

  ctx.fillStyle = muted;
  ctx.textAlign = "center";
  const span = t1 - t0;
  for (let i = 0; i <= 3; i++) {
    const t = t0 + (span * i) / 3;
    const x = mapX(t, t0, t1, x0, x1);
    ctx.fillText(formatTick(t, span), x, h - 6);
  }

  if (visible.length === 0) {
    ctx.fillStyle = muted;
    ctx.textAlign = "center";
    ctx.fillText("Chưa có dữ liệu trong khoảng này", (x0 + x1) / 2, (y0 + y1) / 2);
    return;
  }

  ctx.save();
  ctx.beginPath();
  ctx.rect(x0, y0, x1 - x0, y1 - y0);
  ctx.clip();
  drawSeries(
    ctx, visible, "hum", hRange.min, hRange.max, x0, x1, y0, y1, t0, t1,
    humColor, "rgba(37, 99, 235, 0.10)", [7, 5],
  );
  drawSeries(
    ctx, visible, "temp", tRange.min, tRange.max, x0, x1, y0, y1, t0, t1,
    tempColor, "rgba(15, 118, 110, 0.12)", [],
  );
  ctx.restore();
}

function formatTick(t, span) {
  const d = new Date(t);
  const pad = (n) => String(n).padStart(2, "0");
  if (span <= 15 * 60 * 1000) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
  if (span <= 3 * 60 * 60 * 1000) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function applyTelemetry(msg) {
  if (msg.temp != null) setTemp(msg.temp);
  if (msg.humidity != null) setHum(msg.humidity);
  if (msg.state) stateEl.textContent = msg.state;
  const t = msg.ts || Date.now();
  if (isLiveWindow()) pushPoint(t, lastTemp, lastHum);
  drawChart();
}

function startListenBar(ms) {
  listenBar.classList.remove("hidden");
  listenProgress.max = ms;
  listenEndsAt = Date.now() + ms;
  if (listenTimer) clearInterval(listenTimer);
  listenTimer = setInterval(() => {
    const left = Math.max(0, listenEndsAt - Date.now());
    listenProgress.value = left;
    if (left <= 0) {
      clearInterval(listenTimer);
      listenTimer = null;
    }
  }, 100);
}

function stopListenBar() {
  listenBar.classList.add("hidden");
  if (listenTimer) {
    clearInterval(listenTimer);
    listenTimer = null;
  }
}

function connectMonitor() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/monitor`);
  ws.onopen = () => addLog("Monitor connected");
  ws.onclose = () => {
    addLog("Monitor disconnected, retry…", "err");
    setTimeout(connectMonitor, 1500);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    switch (msg.type) {
      case "snapshot":
        applySnapshot(msg);
        break;
      case "state":
        stateEl.textContent = msg.state;
        break;
      case "telemetry":
        applyTelemetry(msg);
        break;
      case "listen":
        if (msg.state === "start") startListenBar(msg.ms || 5000);
        else stopListenBar();
        break;
      case "log":
        addLog(msg.message, msg.level === "error" ? "err" : "", msg.ts);
        break;
      case "chat":
        addChat(msg.role, msg.text, msg.audio_id, msg.ts);
        break;
      default:
        break;
    }
  };
}

const VERSION_POLL_MS = 4000;
let knownVersion = null;

async function checkFrontendVersion() {
  try {
    const r = await fetch("/api/version", { cache: "no-store" });
    if (!r.ok) return;
    const { version } = await r.json();
    if (!version) return;
    if (knownVersion && version !== knownVersion) {
      addLog("Giao dien moi, dang tai lai…");
      location.reload();
      return;
    }
    knownVersion = version;
  } catch {
    /* backend restarting or briefly unreachable */
  }
}

async function refreshHealth() {
  try {
    const r = await fetch("/api/health", { cache: "no-store" });
    const h = await r.json();
    ollamaPill.textContent = h.cursor_cli_ready
      ? (h.ollama_ready
        ? `Cursor ${h.cursor_cli_model || "Auto"} · Ollama`
        : `Cursor ${h.cursor_cli_model || "Auto"}`)
      : h.ollama_ready
        ? `Ollama ${h.model}`
        : "LLM lỗi";
    ollamaPill.classList.toggle("ok", !!(h.cursor_cli_ready || h.ollama_ready));
    ollamaPill.classList.toggle("bad", !(h.cursor_cli_ready || h.ollama_ready));
  } catch {
    ollamaPill.textContent = "Backend lỗi";
    ollamaPill.classList.add("bad");
  }
}

function toLocalInput(ms) {
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function parseLocalInput(el) {
  const v = el.value;
  if (!v) return null;
  const ms = new Date(v).getTime();
  return Number.isFinite(ms) ? ms : null;
}

async function loadTelemetry() {
  const params = chartWindow === "custom" && customFromMs != null && customToMs != null
    ? `from_ms=${customFromMs}&to_ms=${customToMs}`
    : `window=${encodeURIComponent(chartWindow)}`;
  const r = await fetch(`/api/history/telemetry?${params}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`telemetry ${r.status}`);
  const data = await r.json();
  history.length = 0;
  for (const p of data.points || []) {
    history.push({ t: p.t, temp: p.temp, hum: p.humidity });
  }
  chartFromMs = data.from_ms;
  chartToMs = data.to_ms;
  chartWindowLabel.textContent = RANGE_LABEL[chartWindow] || chartWindow;
  drawChart();
}

async function loadChatHistory() {
  const r = await fetch("/api/history/chat?limit=400", { cache: "no-store" });
  if (!r.ok) return;
  const data = await r.json();
  chatLog.innerHTML = "";
  for (const item of data.items || []) {
    addChat(item.role, item.text, item.audio_id, item.ts);
  }
}

async function loadLogHistory() {
  const r = await fetch("/api/history/logs?limit=400", { cache: "no-store" });
  if (!r.ok) return;
  const data = await r.json();
  eventLog.innerHTML = "";
  for (const item of data.items || []) {
    addLog(item.message, item.level === "error" ? "err" : "", item.ts);
  }
}

async function loadHistory() {
  try {
    await Promise.all([loadTelemetry(), loadChatHistory(), loadLogHistory()]);
  } catch (err) {
    addLog(String(err), "err");
  }
}

function setChartWindow(next) {
  chartWindow = next;
  chartRanges.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.window === next);
  });
  customRange.classList.toggle("hidden", next !== "custom");
  if (next === "custom") {
    const now = Date.now();
    if (!chartFromEl.value) chartFromEl.value = toLocalInput(now - RANGE_MS["1h"]);
    if (!chartToEl.value) chartToEl.value = toLocalInput(now);
    return;
  }
  loadTelemetry().catch((err) => addLog(String(err), "err"));
}

chartRanges.addEventListener("click", (ev) => {
  const btn = ev.target.closest("button[data-window]");
  if (!btn) return;
  setChartWindow(btn.dataset.window);
});

chartApply.addEventListener("click", () => {
  const fromMs = parseLocalInput(chartFromEl);
  const toMs = parseLocalInput(chartToEl);
  if (fromMs == null || toMs == null || toMs <= fromMs) {
    addLog("Khoảng tùy chọn không hợp lệ", "err");
    return;
  }
  customFromMs = fromMs;
  customToMs = toMs;
  chartWindow = "custom";
  loadTelemetry().catch((err) => addLog(String(err), "err"));
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  const btn = chatForm.querySelector("button");
  btn.disabled = true;
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await r.json();
    if (data.error) addLog(data.error, "err");
  } catch (err) {
    addLog(String(err), "err");
  } finally {
    btn.disabled = false;
    chatInput.focus();
  }
});

// ── Firmware panel ──────────────────────────────────────────────────────────
const fwPort = document.getElementById("fwPort");
const fwRefreshPorts = document.getElementById("fwRefreshPorts");
const fwCompile = document.getElementById("fwCompile");
const fwFlash = document.getElementById("fwFlash");
const fwLog = document.getElementById("fwLog");
const fwStatusChip = document.getElementById("fwStatus");

let fwLastCompileOk = false;

function fwSetStatus(text, cls) {
  fwStatusChip.textContent = text;
  fwStatusChip.className = "fw-status-chip" + (cls ? " " + cls : "");
}

function fwAppendLog(line, cls) {
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = line + "\n";
  fwLog.appendChild(span);
  fwLog.scrollTop = fwLog.scrollHeight;
}

async function fwLoadPorts() {
  fwRefreshPorts.disabled = true;
  try {
    const r = await fetch("/api/firmware/ports", { cache: "no-store" });
    const data = await r.json();
    const ports = data.ports || [];
    const prev = fwPort.value;
    while (fwPort.options.length > 1) fwPort.remove(1);
    for (const p of ports) {
      const opt = document.createElement("option");
      opt.value = p.port;
      opt.textContent = p.board ? `${p.port} — ${p.board}` : p.port;
      fwPort.appendChild(opt);
    }
    if (prev && [...fwPort.options].some((o) => o.value === prev)) {
      fwPort.value = prev;
    } else if (ports.length === 1) {
      fwPort.value = ports[0].port;
    }
  } catch (err) {
    fwAppendLog("Lỗi tìm cổng: " + err, "err");
  } finally {
    fwRefreshPorts.disabled = false;
  }
}

async function fwStreamAction(url, payload) {
  fwLog.innerHTML = "";
  fwCompile.disabled = true;
  fwFlash.disabled = true;

  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!r.ok) {
      const err = await r.text();
      fwAppendLog("Lỗi: " + err, "err");
      fwSetStatus("Lỗi", "err");
      return;
    }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n");
      buf = parts.pop();
      for (const part of parts) {
        if (!part.startsWith("data:")) continue;
        const line = part.slice(5).trim();
        if (!line || line === "[DONE]") continue;
        const cls = line.startsWith("✓") ? "ok" : line.startsWith("✗") ? "err" : "";
        fwAppendLog(line, cls);
      }
    }
  } catch (err) {
    fwAppendLog("Lỗi kết nối: " + err, "err");
    fwSetStatus("Lỗi kết nối", "err");
  } finally {
    // Re-check status from server
    try {
      const s = await fetch("/api/firmware/status", { cache: "no-store" });
      const st = await s.json();
      if (st.ok === true) {
        fwSetStatus(st.message || "Hoàn thành", "ok");
        if (st.phase === "idle" && st.message.includes("Biên dịch")) {
          fwLastCompileOk = true;
          fwFlash.disabled = !fwPort.value;
        }
      } else if (st.ok === false) {
        fwSetStatus(st.message || "Lỗi", "err");
      } else {
        fwSetStatus("Sẵn sàng");
      }
    } catch (_) {}
    fwCompile.disabled = false;
    if (fwLastCompileOk) fwFlash.disabled = !fwPort.value;
  }
}

fwRefreshPorts.addEventListener("click", fwLoadPorts);

fwPort.addEventListener("change", () => {
  if (fwLastCompileOk) fwFlash.disabled = !fwPort.value;
});

fwCompile.addEventListener("click", async () => {
  fwSetStatus("Đang biên dịch…", "busy");
  fwLastCompileOk = false;
  fwFlash.disabled = true;
  await fwStreamAction("/api/firmware/compile", {});
});

fwFlash.addEventListener("click", async () => {
  const port = fwPort.value;
  if (!port) { fwAppendLog("Vui lòng chọn cổng COM trước.", "err"); return; }
  fwSetStatus(`Đang nạp lên ${port}…`, "busy");
  await fwStreamAction("/api/firmware/flash", { port });
});

fwLoadPorts();

loadHistory().finally(() => connectMonitor());
refreshHealth();
checkFrontendVersion();
setInterval(refreshHealth, 10000);
setInterval(checkFrontendVersion, VERSION_POLL_MS);
setInterval(() => {
  if (isLiveWindow()) drawChart();
}, 1000);
window.addEventListener("resize", drawChart);
if (window.ResizeObserver) {
  new ResizeObserver(drawChart).observe(chartCanvas.parentElement);
}
drawChart();
