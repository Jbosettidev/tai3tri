import asyncio
import json
import time

from app.config import settings
from app.state import ParkingService


def run(coro):
    return asyncio.run(coro)


def make():
    svc = ParkingService()
    svc.sent = []
    svc.set_sender(lambda cid, p: svc.sent.append((cid, p)))
    svc.backend_xmpp = "CONNECTED"
    return svc


def msg(svc, payload, sender=None):
    return svc.handle_incoming(sender or settings.device_jid, json.dumps(payload))


def test_parking_update_changes_spot_and_history():
    svc = make()
    run(msg(svc, {"type": "parking.update", "device": "esp32-01", "spot": 2, "status": "OCCUPIED"}))
    assert svc.spots[2]["status"] == "OCCUPIED"
    assert svc.spots[2]["occupied_since"] is not None
    assert svc.device["connection"] == "ONLINE"
    assert any(h["spot"] == 2 and h["new"] == "OCCUPIED" for h in svc.history)


def test_invalid_json_and_invalid_fields_are_logged_not_applied():
    svc = make()
    run(svc.handle_incoming(settings.device_jid, "not json"))
    assert svc.messages[-1]["result"] == "JSON inválido"
    assert svc.device["connection"] == "OFFLINE"
    run(msg(svc, {"type": "parking.update", "spot": 9, "status": "OCCUPIED"}))
    assert svc.messages[-1]["result"].startswith("Inválida")
    assert svc.spots[1]["status"] == "UNKNOWN"


def test_other_resource_is_ignored():
    svc = make()
    run(msg(svc, {"type": "parking.update", "spot": 1, "status": "OCCUPIED"},
            sender=f"{settings.bare_jid}/intruso"))
    assert svc.spots[1]["status"] == "UNKNOWN"


def test_command_is_correlated_with_status_response():
    svc = make()

    async def scenario():
        cid = await svc.send_command("status.request")
        await msg(svc, {"type": "device.status", "device": "esp32-01", "commandId": cid,
                        "spots": [{"spot": i, "status": "FREE"} for i in range(1, 5)]})
        return cid

    cid = run(scenario())
    assert svc.commands[cid]["status"] == "OK"
    assert all(s["status"] == "FREE" for s in svc.spots.values())


def test_command_timeout_and_device_offline():
    svc = make()

    async def scenario():
        cid = await svc.send_command("led.test")
        svc._sent[cid] -= 100
        await msg(svc, {"type": "device.online", "device": "esp32-01"})
        svc._seen = time.monotonic() - 100
        await svc.tick()
        return cid

    cid = run(scenario())
    assert svc.commands[cid]["status"] == "TIMEOUT"
    assert svc.device["connection"] == "OFFLINE"


def test_presence_and_returned_message_fail_command():
    svc = make()

    async def scenario():
        await svc.on_device_presence(True)
        assert svc.device["connection"] == "ONLINE"
        await svc.on_device_presence(False)
        assert svc.device["connection"] == "OFFLINE"
        cid = await svc.send_command("status.request")
        await svc.handle_error(cid, "ESP32 offline")
        return cid

    cid = run(scenario())
    assert svc.commands[cid]["status"] == "FAILED"
