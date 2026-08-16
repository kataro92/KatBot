from __future__ import annotations

import json
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope
from pydantic import BaseModel, Field

from .config import WEB_DIR, settings
from .hub import hub
from .ollama_session import OllamaError, OllamaSession
from .pipeline import handle_user_text, on_listen_stop
from .version import web_asset_version


class NoCacheStaticFiles(StaticFiles):
    def is_not_modified(self, response_headers, request_headers) -> bool:
        return False

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("meobot")

session = OllamaSession()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await session.warmup()
        await hub.log("info", f"Ollama ready ({settings.ollama_model})")
    except OllamaError as exc:
        log.warning("Starting without Ollama: %s", exc)
        await hub.log("error", f"Ollama chua san sang: {exc}")
    yield
    await session.close()


app = FastAPI(title="Mèo Bot", lifespan=lifespan)


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@app.get("/api/version")
async def version() -> dict[str, str]:
    return {"version": web_asset_version()}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "ollama_ready": session.ready,
        "ollama_error": session.last_error,
        "model": settings.ollama_model,
        "device_online": hub.device_online,
        "state": hub.state,
        "version": web_asset_version(),
    }


@app.post("/api/chat")
async def chat(body: ChatIn) -> dict[str, str]:
    try:
        reply = await handle_user_text(session, body.text)
    except OllamaError as exc:
        return {"reply": "", "error": str(exc)}
    return {"reply": reply, "error": ""}


@app.websocket("/ws/device")
async def ws_device(ws: WebSocket) -> None:
    await ws.accept()
    sid = await hub.attach_device(ws)
    await ws.send_text(
        json.dumps(
            {
                "type": "hello",
                "transport": "websocket",
                "session_id": sid,
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": 8000,
                    "channels": 1,
                    "bits": 16,
                },
            }
        )
    )
    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                hub.add_audio(message["bytes"])
                continue
            text = message.get("text")
            if not text:
                continue
            await _handle_device_json(text)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.detach_device(ws)


async def _handle_device_json(raw: str) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await hub.log("warn", "Device sent invalid JSON")
        return
    kind = msg.get("type")
    if kind == "hello":
        await hub.log("info", "Device hello")
        await hub.broadcast({"type": "hello", "from": "device", "payload": msg})
    elif kind == "listen":
        state = msg.get("state")
        if state == "start":
            hub.start_listen()
            await hub.set_state("listening")
            await hub.log("info", "Listen 5s start")
            await hub.broadcast({"type": "listen", "state": "start", "ms": 5000})
        elif state == "stop":
            await hub.broadcast({"type": "listen", "state": "stop"})
            asyncio.create_task(on_listen_stop(session))
    elif kind == "telemetry":
        if "temp" in msg:
            try:
                hub.temp = float(msg["temp"])
            except (TypeError, ValueError):
                pass
        if "humidity" in msg:
            try:
                hub.humidity = float(msg["humidity"])
            except (TypeError, ValueError):
                pass
        if msg.get("state"):
            hub.state = str(msg["state"])
        await hub.broadcast(
            {
                "type": "telemetry",
                "temp": hub.temp,
                "humidity": hub.humidity,
                "state": hub.state,
            }
        )
    elif kind == "abort":
        hub.stop_listen()
        await hub.set_state("idle")
        await hub.send_device({"type": "state", "value": "idle"})
        await hub.log("info", "Device abort")
    else:
        await hub.log("debug", f"Device msg {kind}")


@app.websocket("/ws/monitor")
async def ws_monitor(ws: WebSocket) -> None:
    await ws.accept()
    await hub.attach_monitor(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.detach_monitor(ws)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(
        WEB_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


app.mount("/static", NoCacheStaticFiles(directory=str(WEB_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
