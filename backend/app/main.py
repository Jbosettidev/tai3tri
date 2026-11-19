import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.state import ParkingService
from app.xmpp_client import ParkingXmpp, probe_prosody

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
clients = set()                      # WebSockets do painel


async def broadcast(message: dict) -> None:
    for ws in list(clients):
        try:
            await ws.send_json(message)
        except Exception:  # noqa: BLE001
            clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc, xmpp = ParkingService(), None
    xmpp = ParkingXmpp(svc)
    svc.set_notifier(broadcast)
    svc.set_sender(xmpp.send_json)
    app.state.svc = svc
    # Tudo no mesmo event loop: Slixmpp (asyncio) + FastAPI + tarefas de apoio.
    tasks = [asyncio.create_task(xmpp.supervise()),
             asyncio.create_task(probe_prosody(svc)),
             asyncio.create_task(svc.watchdog())]
    yield
    for t in tasks:
        t.cancel()
    xmpp.disconnect()


app = FastAPI(title="Estacionamento Inteligente", lifespan=lifespan)


# ---------- REST ----------
@app.get("/api/estado")
async def estado():
    return app.state.svc.snapshot()


@app.get("/api/vagas")
async def vagas():
    return app.state.svc.snapshot()["spots"]


@app.get("/api/historico")
async def historico():
    return app.state.svc.snapshot()["history"]


@app.get("/api/xmpp/mensagens")
async def mensagens():
    return app.state.svc.snapshot()["messages"]


async def _command(ctype: str) -> dict:
    try:
        cid = await app.state.svc.send_command(ctype)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"commandId": cid, "status": "PENDING"}


@app.post("/api/comandos/status", status_code=202)
async def cmd_status():
    return await _command("status.request")


@app.post("/api/comandos/led-test", status_code=202)
async def cmd_led():
    return await _command("led.test")


@app.post("/api/comandos/sensor-read", status_code=202)
async def cmd_sensor():
    return await _command("sensor.read")


@app.get("/api/comandos/{command_id}")
async def comando(command_id: str):
    c = app.state.svc.commands.get(command_id)
    if not c:
        raise HTTPException(status_code=404, detail="comando não encontrado")
    return c


# ---------- WebSocket (tempo real p/ o painel) ----------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json({"event": "snapshot", "data": app.state.svc.snapshot()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
