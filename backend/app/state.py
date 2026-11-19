"""Estado em RAM (sem banco): vagas, histórico, log XMPP e comandos."""
import asyncio
import itertools
import json
import time
import uuid
from collections import deque
from datetime import datetime

from app.config import NUM_SPOTS, settings

STATUSES = ("FREE", "OCCUPIED", "FAULT")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _spot(d: dict):
    """Valida {spot, status, distanceCm?} vindo do ESP32."""
    n, st = d.get("spot"), d.get("status", "FAULT")
    if not isinstance(n, int) or not 1 <= n <= NUM_SPOTS or st not in STATUSES:
        raise ValueError("vaga/status inválido")
    return n, st, d.get("distanceCm")


class ParkingService:
    def __init__(self) -> None:
        self.spots = {n: {"spot": n, "status": "UNKNOWN", "last_change": None,
                          "occupied_since": None, "distance_cm": None}
                      for n in range(1, NUM_SPOTS + 1)}
        self.history = deque(maxlen=100)      # eventos (RAM)
        self.messages = deque(maxlen=100)     # log das mensagens XMPP (RAM)
        self.commands = {}                    # commandId -> estado do comando
        self.device = {"id": settings.device_id, "connection": "OFFLINE", "last_seen": None}
        self.backend_xmpp = "DISCONNECTED"
        self.prosody = "DISCONNECTED"

        self._seen = None                     # monotonic da última msg do ESP32
        self._sent = {}                       # commandId -> monotonic do envio
        self._log_entry = {}                  # commandId -> entrada do log
        self._notify = None                   # async fn(dict)  -> WebSocket
        self._sender = None                   # fn(commandId, dict) -> XMPP
        self._cmd_seq = itertools.count(1)
        self._msg_seq = itertools.count(1)

    def set_notifier(self, fn): self._notify = fn
    def set_sender(self, fn): self._sender = fn

    async def _emit(self) -> None:
        if self._notify:
            await self._notify({"event": "snapshot", "data": self.snapshot()})

    def snapshot(self) -> dict:
        return {"server_time": now_iso(),
                "spots": [dict(s) for s in self.spots.values()],
                "history": list(reversed(self.history))[:50],
                "device": dict(self.device),
                "xmpp": {"prosody": self.prosody, "backend": self.backend_xmpp,
                         "device": self.device["connection"]},
                "messages": list(reversed(self.messages))[:50]}

    # ---------- log das mensagens XMPP ----------
    def _log(self, direction, mtype, src, dst, summary="", result=None, cid=None) -> dict:
        e = {"id": next(self._msg_seq), "direction": direction, "type": mtype, "from": src,
             "to": dst, "time": now_iso(), "summary": summary, "result": result, "commandId": cid}
        self.messages.append(e)
        return e

    # ---------- conexão ----------
    async def on_prosody(self, ok: bool) -> None:
        new = "CONNECTED" if ok else "DISCONNECTED"
        if new != self.prosody:
            self.prosody = new
            await self._emit()

    async def on_backend_xmpp(self, ok: bool) -> None:
        new = "CONNECTED" if ok else "DISCONNECTED"
        if new == self.backend_xmpp:
            return
        self.backend_xmpp = new
        await self._emit()
        if ok:    # ao (re)conectar, pede o estado completo ao ESP32
            await self.try_command("status.request")

    async def on_device_presence(self, online: bool) -> None:
        """Presença XMPP do resource do ESP32 (aviso imediato de entrada/saída)."""
        if online:
            self._touch_device()
        elif self.device["connection"] != "OFFLINE":
            self._set_device_offline()
        await self._emit()

    def _touch_device(self) -> None:
        self._seen = time.monotonic()
        self.device["last_seen"] = now_iso()
        if self.device["connection"] != "ONLINE":
            self.device["connection"] = "ONLINE"
            self._event("device.online")

    def _set_device_offline(self) -> None:
        self.device["connection"] = "OFFLINE"
        self._event("device.offline")

    def _event(self, etype, spot=None, prev=None, new=None) -> None:
        self.history.append({"time": now_iso(), "type": etype, "spot": spot,
                             "previous": prev, "new": new})

    def _apply(self, spot, new, distance=None, source="parking.update") -> bool:
        s = self.spots[spot]
        if distance is not None:
            s["distance_cm"] = distance
        old = s["status"]
        if old == new:
            return False
        t = now_iso()
        s.update(status=new, last_change=t, occupied_since=t if new == "OCCUPIED" else None)
        self._event(source, spot, old, new)
        return True

    # ---------- mensagens recebidas ----------
    async def handle_incoming(self, sender: str, body: str) -> None:
        label = settings.device_id.upper() if sender == settings.device_jid else sender
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._log("RECEBIDA", "invalid", label, "Backend", body[:80], "JSON inválido")
            await self._emit()
            return

        mtype = str(data.get("type", "?"))
        entry = self._log("RECEBIDA", mtype, label, "Backend", self._summary(data))
        if sender != settings.device_jid:          # só o resource do ESP32 é aceito
            entry["result"] = "Ignorada: remetente não autorizado"
            await self._emit()
            return

        self._touch_device()
        try:
            entry["result"] = await self._dispatch(mtype, data)
        except (ValueError, TypeError, KeyError) as exc:
            entry["result"] = f"Inválida: {exc}"
        await self._emit()

    async def handle_error(self, cid: str, reason: str) -> None:
        """Erro devolvido pelo Prosody (ou mensagem que voltou sem destinatário)."""
        self._log("RECEBIDA", "xmpp.error", "Prosody", "Backend",
                  f"commandId={cid}" if cid else "", reason, cid or None)
        if cid:
            await self._resolve(cid, "FAILED", reason)
        await self._emit()

    @staticmethod
    def _summary(d: dict) -> str:
        if "spot" in d:
            return f"Vaga {d['spot']}: {d.get('status', '?')}"
        if isinstance(d.get("spots"), list):
            return ", ".join(f"V{s.get('spot')}={s.get('status')}" for s in d["spots"] if isinstance(s, dict))
        return f"commandId={d['commandId']}" if "commandId" in d else ""

    async def _dispatch(self, mtype: str, d: dict) -> str:
        if mtype == "parking.update":
            n, st, dist = _spot(d)
            self._apply(n, st, dist)
            return f"Vaga {n} → {st}"
        if mtype == "sensor.error":
            n, _, _ = _spot({**d, "status": "FAULT"})
            self._apply(n, "FAULT", None, "sensor.error")
            return f"Vaga {n} em falha"
        if mtype == "device.online":
            await self.try_command("status.request")
            return "Dispositivo online; status solicitado"
        if mtype == "device.status":
            items = [_spot(s) for s in d["spots"]]
            changed = sum(self._apply(n, st, dist, "device.status") for n, st, dist in items)
            if d.get("commandId"):
                await self._resolve(d["commandId"], "OK", f"{len(items)} vagas")
            return f"{len(items)} vagas ({changed} alteradas)"
        if mtype == "command.ack":
            ok = bool(d.get("ok", True))
            await self._resolve(d["commandId"], "OK" if ok else "FAILED", d.get("detail") or d.get("command"))
            return "Comando concluído" if ok else f"Comando falhou: {d.get('detail')}"
        return "Tipo desconhecido"

    # ---------- comandos (painel -> backend -> XMPP -> ESP32) ----------
    async def send_command(self, ctype: str) -> str:
        if self._sender is None or self.backend_xmpp != "CONNECTED":
            raise RuntimeError("Backend sem sessão XMPP com o Prosody")
        cid = f"cmd-{next(self._cmd_seq):03d}-{uuid.uuid4().hex[:4]}"
        self._log_entry[cid] = self._log("ENVIADA", ctype, "Backend", settings.device_id.upper(),
                                         f"commandId={cid}", "aguardando resposta", cid)
        self.commands[cid] = {"commandId": cid, "type": ctype, "status": "PENDING",
                              "sent_at": now_iso(), "finished_at": None, "detail": None}
        self._sent[cid] = time.monotonic()
        while len(self.commands) > 50:             # limite de memória
            old = next(iter(self.commands))
            for dct in (self.commands, self._sent, self._log_entry):
                dct.pop(old, None)
        self._sender(cid, {"type": ctype, "commandId": cid})
        await self._emit()
        return cid

    async def try_command(self, ctype: str) -> None:
        try:
            await self.send_command(ctype)
        except RuntimeError:
            pass

    async def _resolve(self, cid: str, status: str, detail=None) -> None:
        c = self.commands.get(cid)
        if not c or c["status"] != "PENDING":
            return
        c.update(status=status, detail=detail, finished_at=now_iso())
        e = self._log_entry.get(cid)
        if e:
            e["result"] = {"OK": "concluído", "FAILED": "falhou", "TIMEOUT": "timeout"}[status] + \
                          (f" — {detail}" if detail else "")
        if self._notify:
            await self._notify({"event": "command.result", "data": dict(c)})

    # ---------- watchdog (ESP32 offline + timeout de comandos) ----------
    async def tick(self) -> None:
        now, changed = time.monotonic(), False
        if (self.device["connection"] == "ONLINE" and self._seen is not None
                and now - self._seen > settings.offline_after_s):
            self._set_device_offline()
            changed = True
        for cid, c in list(self.commands.items()):
            if c["status"] == "PENDING" and now - self._sent.get(cid, now) > settings.command_timeout_s:
                await self._resolve(cid, "TIMEOUT", "sem resposta do ESP32")
                changed = True
        if changed:
            await self._emit()

    async def watchdog(self) -> None:
        while True:
            await asyncio.sleep(1)
            await self.tick()
