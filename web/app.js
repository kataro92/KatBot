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

let listenTimer = null;
let listenEndsAt = 0;

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
  devicePill.textContent = online ? "ESP online" : "ESP offline";
  devicePill.classList.toggle("ok", online);
  devicePill.classList.toggle("bad", !online);
}

function applySnapshot(msg) {
  setDeviceOnline(!!msg.device_online);
  stateEl.textContent = msg.state || "offline";
  tempEl.textContent = msg.temp == null ? "—" : `${msg.temp.toFixed(1)} °C`;
  humidityEl.textContent = msg.humidity == null ? "—" : `${msg.humidity.toFixed(0)} %`;
  sessionEl.textContent = msg.session_id || "—";
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
        if (msg.temp != null) tempEl.textContent = `${Number(msg.temp).toFixed(1)} °C`;
        if (msg.humidity != null) humidityEl.textContent = `${Number(msg.humidity).toFixed(0)} %`;
        if (msg.state) stateEl.textContent = msg.state;
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

async function refreshHealth() {
  try {
    const r = await fetch("/api/health");
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
setInterval(refreshHealth, 10000);
