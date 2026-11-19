"""Cliente XMPP do backend (Slixmpp), no MESMO event loop do FastAPI.

Conta única no Prosody: o backend entra como  <conta>/backend  e o ESP32 como  <conta>/esp32.
As mensagens vão de resource para resource (JID completo)."""
import asyncio
import inspect
import json
import logging

import slixmpp

from app.config import settings

log = logging.getLogger("xmpp")


def start_connect(xmpp: slixmpp.ClientXMPP, host: str, port: int) -> None:
    """Compatível com connect() do slixmpp 1.7 (address) e 1.8+ (host, port)."""
    if "address" in inspect.signature(xmpp.connect).parameters:
        xmpp.connect(address=(host, port))
    else:
        xmpp.connect(host=host, port=port)


def allow_plain_lan(xmpp: slixmpp.ClientXMPP) -> None:
    """Protótipo em LAN: sem TLS (o Prosody precisa de c2s_require_encryption = false)."""
    xmpp.enable_starttls = False
    xmpp.enable_direct_tls = False
    xmpp.enable_plaintext = True
    xmpp.auto_reconnect = False          # quem reconecta é o supervise()
    xmpp["feature_mechanisms"].unencrypted_plain = True


class ParkingXmpp(slixmpp.ClientXMPP):
    def __init__(self, svc) -> None:
        super().__init__(settings.backend_jid, settings.password)
        self.svc = svc
        self.session_ok = False
        self._connecting = False
        self._started_at = 0.0

        self.register_plugin("xep_0199", {"keepalive": True, "interval": 30, "timeout": 10})
        allow_plain_lan(self)

        self.add_event_handler("session_start", self._on_start)
        self.add_event_handler("message", self._on_message)
        self.add_event_handler("presence_available", self._on_presence)
        self.add_event_handler("presence_unavailable", self._on_presence)
        self.add_event_handler("disconnected", self._on_disconnected)
        self.add_event_handler("connection_failed", self._on_failed)
        self.add_event_handler("failed_auth", self._on_auth_failed)

    # ---- eventos ----
    async def _on_start(self, _event) -> None:
        self.send_presence()
        self.session_ok = True
        self._connecting = False
        log.info("sessão XMPP ativa como %s", settings.backend_jid)
        await self.svc.on_backend_xmpp(True)

    async def _on_disconnected(self, _event) -> None:
        self.session_ok = False
        self._connecting = False
        log.warning("sessão XMPP encerrada")
        await self.svc.on_backend_xmpp(False)

    async def _on_failed(self, _event) -> None:
        self._connecting = False
        log.warning("não consegui conectar no Prosody (%s:%s)", settings.host, settings.port)

    async def _on_auth_failed(self, _event) -> None:
        self._connecting = False
        log.error("autenticação recusada: confira XMPP_JID/XMPP_PASSWORD e se o prosody.cfg.lua "
                  "tem  c2s_require_encryption = false  e  allow_unencrypted_plain_auth = true")

    async def _on_presence(self, pres) -> None:
        if pres["from"].full == settings.device_jid:      # presença do resource do ESP32
            await self.svc.on_device_presence(pres["type"] != "unavailable")

    async def _on_message(self, msg) -> None:
        if msg["type"] == "error":
            await self.svc.handle_error(msg["id"], msg["error"]["condition"])
            return
        if msg["type"] not in ("chat", "normal") or not msg["body"]:
            return
        sender = msg["from"].full
        if sender == settings.backend_jid:
            # Prosody devolveu a nossa própria mensagem: o resource do ESP32 não está online.
            await self.svc.handle_error(msg["id"], "ESP32 offline (sem resource esp32 na conta)")
            return
        await self.svc.handle_incoming(sender, msg["body"])

    # ---- envio ----
    def send_json(self, command_id: str, payload: dict) -> None:
        m = self.make_message(mto=settings.device_jid, mbody=json.dumps(payload), mtype="chat")
        m["id"] = command_id
        m.send()

    # ---- supervisão / reconexão ----
    async def supervise(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            now = loop.time()
            if not self.session_ok and (not self._connecting or now - self._started_at > 15):
                if self._connecting:
                    try:
                        self.abort()
                    except Exception:  # noqa: BLE001
                        pass
                self._connecting, self._started_at = True, now
                try:
                    start_connect(self, settings.host, settings.port)
                except Exception:  # noqa: BLE001
                    log.exception("erro ao iniciar conexão")
                    self._connecting = False
            await asyncio.sleep(3)


async def probe_prosody(svc) -> None:
    """Sonda TCP real na porta do Prosody (indicador 'Servidor Prosody' do painel)."""
    while True:
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(settings.host, settings.port), 2)
            w.close()
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        await svc.on_prosody(ok)
        await asyncio.sleep(5)
