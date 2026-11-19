"""ESP32 simulado (mesmo protocolo XMPP) p/ testar sem hardware.
Uso (dentro de backend/):  python -m tools.fake_esp32
Entra na MESMA conta do Prosody, com resource 'esp32'."""
import asyncio
import json
import random

import slixmpp

from app.config import settings
from app.xmpp_client import allow_plain_lan, start_connect


class FakeEsp(slixmpp.ClientXMPP):
    def __init__(self):
        super().__init__(settings.device_jid, settings.password)
        allow_plain_lan(self)
        self.auto_reconnect = True
        self.states = ["FREE"] * 4
        self.add_event_handler("session_start", self.on_start)
        self.add_event_handler("message", self.on_message)

    def to_backend(self, payload):
        self.send_message(mto=settings.backend_jid, mbody=json.dumps(payload), mtype="chat")

    def status(self, cid=None):
        p = {"type": "device.status", "device": settings.device_id,
             "spots": [{"spot": i + 1, "status": s} for i, s in enumerate(self.states)]}
        if cid:
            p["commandId"] = cid
        self.to_backend(p)

    async def on_start(self, _):
        self.send_presence()
        self.to_backend({"type": "device.online", "device": settings.device_id})
        self.status()
        asyncio.create_task(self.simulate())

    async def simulate(self):
        while True:
            await asyncio.sleep(6)
            i = random.randrange(4)
            self.states[i] = "OCCUPIED" if self.states[i] == "FREE" else "FREE"
            self.to_backend({"type": "parking.update", "device": settings.device_id,
                             "spot": i + 1, "status": self.states[i]})
            self.status()   # heartbeat

    def on_message(self, msg):
        if msg["type"] not in ("chat", "normal") or not msg["body"]:
            return
        if msg["from"].full != settings.backend_jid:     # só aceita comandos do backend
            return
        data = json.loads(msg["body"])
        cid, t = data.get("commandId", ""), data.get("type")
        if t in ("status.request", "sensor.read"):
            self.status(cid)
        elif t == "led.test":
            self.to_backend({"type": "command.ack", "device": settings.device_id,
                             "commandId": cid, "command": t, "ok": True})


async def main():
    esp = FakeEsp()
    start_connect(esp, settings.host, settings.port)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
