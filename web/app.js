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

let listenTimer = null;
let listenEndsAt = 0;
let deviceOnline = false;
let lastTemp = null;
let lastHum = null;

const WINDOW_MS = 3 * 60 * 1000;
const SAMPLE_MS = 1000;
const history = []; // { t, temp, hum }

function addLog(message, cls) {
  const li = document.createElement("li");
  if (cls) li.className = cls;
  const ts = new Date().toLocaleTimeString();
  li.textContent = `${ts}  ${message}`;
  eventLog.prepend(li);
  while (eventLog.children.length > 200) eventLog.lastChild.remove();
}

function addChat(role, text) {
  const li = document.createElement("li");
  li.className = role;
  li.textContent = `${role === "user" ? "Bạn" : "Mèo"}: ${text}`;
  chatLog.prepend(li);
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

function pushSample(now = Date.now()) {
  history.push({ t: now, temp: lastTemp, hum: lastHum });
  const cut = now - WINDOW_MS - SAMPLE_MS;
  while (history.length && history[0].t < cut) history.shift();
}

function applySnapshot(msg) {
  setDeviceOnline(!!msg.device_online);
  stateEl.textContent = msg.state || "offline";
  if (msg.temp != null) setTemp(msg.temp);
  if (msg.humidity != null) setHum(msg.humidity);
  sessionEl.textContent = msg.session_id ? `phiên ${msg.session_id}` : "phiên —";
  if (deviceOnline && (lastTemp != null || lastHum != null)) {
    pushSample();
    drawChart();
  }
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

function drawSeries(ctx, pts, key, yMin, yMax, x0, x1, y0, y1, t0, t1, stroke, fill) {
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
    ctx.lineTo(lastX, y1);
    ctx.lineTo(mapX(usable[0].t, t0, t1, x0, x1), y1);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.beginPath();
    usable.forEach((p, i) => {
      const x = mapX(p.t, t0, t1, x0, x1);
      const y = mapY(p[key], yMin, yMax, y0, y1);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
  }
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.8;
  ctx.lineJoin = "round";
  ctx.stroke();
  ctx.fillStyle = stroke;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 3.2, 0, Math.PI * 2);
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
  const now = Date.now();
  const t1 = now;
  const t0 = now - WINDOW_MS;

  ctx.fillStyle = "#0e1016";
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = "#2a3140";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.rect(x0, y0, x1 - x0, y1 - y0);
  ctx.stroke();

  const temps = history.map((p) => p.temp).filter((v) => v != null);
  const hums = history.map((p) => p.hum).filter((v) => v != null);
  const tRange = niceRange(Math.min(...temps), Math.max(...temps), 15, 35);
  const hRange = niceRange(Math.min(...hums), Math.max(...hums), 30, 80);

  ctx.font = "11px Segoe UI, system-ui, sans-serif";
  ctx.fillStyle = "#9aa3b2";
  for (let i = 0; i <= 4; i++) {
    const y = y0 + ((y1 - y0) * i) / 4;
    ctx.strokeStyle = "#1c2230";
    ctx.beginPath();
    ctx.moveTo(x0, y);
    ctx.lineTo(x1, y);
    ctx.stroke();
    const tv = tRange.max - ((tRange.max - tRange.min) * i) / 4;
    const hv = hRange.max - ((hRange.max - hRange.min) * i) / 4;
    ctx.textAlign = "right";
    ctx.fillStyle = "#c8e07a";
    ctx.fillText(tv.toFixed(1), x0 - 6, y + 3);
    ctx.textAlign = "left";
    ctx.fillStyle = "#7cb7ff";
    ctx.fillText(hv.toFixed(0), x1 + 6, y + 3);
  }

  ctx.fillStyle = "#9aa3b2";
  ctx.textAlign = "center";
  for (let i = 0; i <= 3; i++) {
    const t = t0 + ((t1 - t0) * i) / 3;
    const x = mapX(t, t0, t1, x0, x1);
    const d = new Date(t);
    const label = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
    ctx.fillText(label, x, h - 6);
  }

  const visible = history.filter((p) => p.t >= t0);
  if (visible.length === 0) {
    ctx.fillStyle = "#9aa3b2";
    ctx.textAlign = "center";
    ctx.fillText(deviceOnline ? "Chờ cảm biến DHT…" : "ESP offline — chờ kết nối", (x0 + x1) / 2, (y0 + y1) / 2);
    return;
  }

  ctx.save();
  ctx.beginPath();
  ctx.rect(x0, y0, x1 - x0, y1 - y0);
  ctx.clip();
  drawSeries(ctx, visible, "hum", hRange.min, hRange.max, x0, x1, y0, y1, t0, t1, "#7cb7ff", "rgba(124,183,255,0.12)");
  drawSeries(ctx, visible, "temp", tRange.min, tRange.max, x0, x1, y0, y1, t0, t1, "#c8e07a", "rgba(200,224,122,0.14)");
  ctx.restore();
}

function applyTelemetry(msg) {
  if (msg.temp != null) setTemp(msg.temp);
  if (msg.humidity != null) setHum(msg.humidity);
  if (msg.state) stateEl.textContent = msg.state;
  pushSample();
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
        addLog(msg.message, msg.level === "error" ? "err" : "");
        break;
      case "chat":
        addChat(msg.role, msg.text);
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
    ollamaPill.textContent = h.ollama_ready
      ? `Ollama ${h.model}`
      : "Ollama lỗi";
    ollamaPill.classList.toggle("ok", !!h.ollama_ready);
    ollamaPill.classList.toggle("bad", !h.ollama_ready);
  } catch {
    ollamaPill.textContent = "Backend lỗi";
    ollamaPill.classList.add("bad");
  }
}

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

connectMonitor();
refreshHealth();
checkFrontendVersion();
setInterval(refreshHealth, 10000);
setInterval(checkFrontendVersion, VERSION_POLL_MS);
setInterval(() => {
  if (deviceOnline && (lastTemp != null || lastHum != null)) pushSample();
  drawChart();
}, SAMPLE_MS);
window.addEventListener("resize", drawChart);
if (window.ResizeObserver) {
  new ResizeObserver(drawChart).observe(chartCanvas.parentElement);
}
drawChart();
