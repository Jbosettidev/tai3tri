const $ = (id) => document.getElementById(id);
const TXT = { FREE: "Livre", OCCUPIED: "Ocupada", FAULT: "Falha", UNKNOWN: "Sem dados" };
const CONN = { CONNECTED: "CONECTADO", DISCONNECTED: "DESCONECTADO", ONLINE: "ONLINE", OFFLINE: "OFFLINE" };
const EVENTS = { "parking.update": "Atualização", "sensor.error": "Falha de sensor", "device.status": "Relatório",
                 "device.online": "Dispositivo online", "device.offline": "Dispositivo offline" };

let state = null;
let clockOffset = 0;   // relógio do servidor - relógio do navegador

// Sempre textContent (dados vêm do dispositivo): sem risco de injeção de HTML.
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}
const nowMs = () => Date.now() + clockOffset;
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString("pt-BR") : "—");
function fmtDur(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? h + "h " : "") + (h || m ? m + "min " : "") + s + "s";
}
function setBadge(node, value) {
  node.textContent = CONN[value] || value;
  node.className = "badge " + (value === "CONNECTED" || value === "ONLINE" ? "on" : "off");
}

function renderSpots() {
  if (!state) return;
  const box = $("spots");
  box.replaceChildren();
  const stale = state.device.connection !== "ONLINE";
  for (const s of state.spots) {
    const c = el("div", "spot " + s.status + (stale ? " stale" : ""));
    c.append(el("div", "num", "Vaga " + String(s.spot).padStart(2, "0")), el("div", "st", TXT[s.status] || s.status));
    const tm = s.status === "OCCUPIED" && s.occupied_since
      ? "há " + fmtDur((nowMs() - Date.parse(s.occupied_since)) / 1000) : "";
    c.append(el("div", "tm", tm));
    box.append(c);
  }
}

function renderDevice() {
  if (!state) return;
  setBadge($("dev-badge"), state.device.connection);
  $("dev-seen").textContent = fmtTime(state.device.last_seen);
}

function renderXmpp() {
  setBadge($("x-prosody"), state.xmpp.prosody);
  setBadge($("x-backend"), state.xmpp.backend);
  setBadge($("x-device"), state.xmpp.device);
  const box = $("messages");
  box.replaceChildren();
  for (const m of state.messages) {
    const d = el("div", "msg " + m.direction);
    d.append(el("div", "tag", "[" + m.direction + "]"), el("div", null, m.type),
             el("div", "meta", m.from + " -> " + m.to + " · " + fmtTime(m.time)));
    if (m.summary) d.append(el("div", null, m.summary));
    if (m.result) d.append(el("div", "meta", "Resultado: " + m.result));
    box.append(d);
  }
}

function renderHistory() {
  const body = $("history");
  body.replaceChildren();
  for (const h of state.history) {
    const tr = el("tr");
    const lbl = (v) => (v ? TXT[v] || v : "—");
    for (const v of [fmtTime(h.time), EVENTS[h.type] || h.type, h.spot ? "Vaga " + h.spot : "—", lbl(h.previous), lbl(h.new)])
      tr.append(el("td", null, v));
    body.append(tr);
  }
}

function render() {
  if (!state) return;
  renderSpots(); renderDevice(); renderXmpp(); renderHistory();
}

let toastTimer;
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 6000);
}

async function sendCommand(path, label, btn) {
  btn.disabled = true;
  try {
    const r = await fetch(path, { method: "POST" });
    const j = await r.json();
    toast(r.ok ? label + ": enviado, aguardando resposta…" : label + ": " + (j.detail || "erro"));
  } catch (e) {
    toast(label + ": falha de rede");
  } finally {
    setTimeout(() => (btn.disabled = false), 800);
  }
}
$("btn-status").onclick = (e) => sendCommand("/api/comandos/status", "Atualizar vagas", e.target);
$("btn-led").onclick = (e) => sendCommand("/api/comandos/led-test", "Teste de LEDs", e.target);

function connect() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => { $("ws-badge").textContent = "painel: conectado"; $("ws-badge").className = "badge on"; };
  ws.onclose = () => {
    $("ws-badge").textContent = "painel: desconectado"; $("ws-badge").className = "badge off";
    setTimeout(connect, 2000);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.event === "snapshot") {
      state = msg.data;
      clockOffset = Date.parse(state.server_time) - Date.now();
      render();
    } else if (msg.event === "command.result") {
      const c = msg.data;
      const r = { OK: "concluído ✔", FAILED: "falhou ✖", TIMEOUT: "timeout (sem resposta do ESP32)" }[c.status] || c.status;
      toast(c.type + ": " + r + (c.detail ? " — " + c.detail : ""));
    }
  };
}

setInterval(() => { renderSpots(); }, 1000);   // contador de tempo de ocupação
connect();
