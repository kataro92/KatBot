from __future__ import annotations

import json
import logging
import asyncio
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope
from pydantic import BaseModel, Field

from .config import WEB_DIR, settings
from .hub import hub
from .ollama_session import OllamaError, OllamaSession
from .cursor_cli import CursorCliError, probe_cursor_cli
from .clips import get_pcm, pcm16_to_wav
from .pipeline import handle_user_text, on_listen_stop
from .store import close_store, db, init_store, window_bounds
from . import stt as stt_mod
from .version import web_asset_version
from . import firmware as fw_mod


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


def _stt_engine_label() -> str:
    try:
        return stt_mod.stt_engine_name()
    except ValueError:
        return (settings.stt_engine or "").strip() or "unknown"


def _stt_model_label() -> str:
    try:
        engine = stt_mod.stt_engine_name()
    except ValueError:
        return settings.whisper_model
    if engine == "phowhisper":
        return settings.phowhisper_model
    if engine == "elevenlabs":
        return settings.elevenlabs_stt_model or "scribe_v2"
    return settings.whisper_model


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(init_store, settings.db_path)
    if settings.cursor_cli_enabled:
        try:
            await asyncio.to_thread(probe_cursor_cli)
            session.cursor_ready = True
            session.cursor_error = None
            await hub.log(
                "info",
                f"Cursor CLI ready (model {settings.cursor_cli_model})",
            )
        except CursorCliError as exc:
            session.cursor_ready = False
            session.cursor_error = str(exc)
            log.warning("Cursor CLI not ready: %s", exc)
            await hub.log("warn", f"Cursor CLI chua san sang, dung Ollama: {exc}")
    try:
        await session.warmup()
        await hub.log("info", f"Ollama ready ({settings.ollama_model})")
    except OllamaError as exc:
        log.warning("Starting without Ollama: %s", exc)
        await hub.log("error", f"Ollama chua san sang: {exc}")
    log.info("Listen window %s ms", settings.listen_ms)
    await hub.log("info", f"Listen window {settings.listen_ms} ms")
    try:
        await asyncio.to_thread(stt_mod._get_model)
        await hub.log("info", f"STT ready ({stt_mod._model_label})")
    except Exception as exc:
        log.warning("STT warmup failed: %s", exc)
        await hub.log("warn", f"STT chua san sang: {exc}")
    yield
    await session.close()
    await asyncio.to_thread(close_store)


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
        "cursor_cli_ready": session.cursor_ready,
        "cursor_cli_error": session.cursor_error,
        "cursor_cli_model": settings.cursor_cli_model,
        "model": settings.ollama_model,
        "device_online": hub.device_online,
        "state": hub.state,
        "temp": hub.temp,
        "humidity": hub.humidity,
        "web_search": settings.web_search_enabled,
        "listen_ms": settings.listen_ms,
        "stt_engine": _stt_engine_label(),
        "stt_model": _stt_model_label(),
        "version": web_asset_version(),
    }


@app.get("/api/history/telemetry")
async def history_telemetry(
    window: str = "15m",
    from_ms: int | None = None,
    to_ms: int | None = None,
) -> dict[str, Any]:
    try:
        start, end = window_bounds(window, from_ms, to_ms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    points = await asyncio.to_thread(db().telemetry, start, end)
    return {"from_ms": start, "to_ms": end, "points": points}


@app.get("/api/history/chat")
async def history_chat(limit: int = 300) -> dict[str, Any]:
    items = await asyncio.to_thread(db().chat, limit=limit)
    return {"items": items}


@app.get("/api/history/logs")
async def history_logs(limit: int = 300) -> dict[str, Any]:
    items = await asyncio.to_thread(db().logs, limit=limit)
    return {"items": items}


@app.get("/api/clips/{clip_id}")
async def clip_wav(clip_id: str) -> Response:
    item = get_pcm(clip_id)
    if item is None:
        raise HTTPException(status_code=404, detail="clip not found")
    pcm, hz = item
    return Response(
        content=pcm16_to_wav(pcm, hz),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/firmware/ports")
async def firmware_ports() -> dict:
    ports = await fw_mod.list_ports()
    return {"ports": ports}


@app.get("/api/firmware/status")
async def firmware_status() -> dict:
    return fw_mod.get_status()


@app.post("/api/firmware/compile")
async def firmware_compile() -> StreamingResponse:
    return StreamingResponse(
        fw_mod.run_compile(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


class FlashIn(BaseModel):
    port: str = Field(min_length=1, max_length=32)


@app.post("/api/firmware/flash")
async def firmware_flash(body: FlashIn) -> StreamingResponse:
    port = body.port.strip()
    if not re.match(r"^(COM\d+|/dev/[\w./-]+)$", port, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="invalid port")
    return StreamingResponse(
        fw_mod.run_flash(port),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


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
                "listen_ms": settings.listen_ms,
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
        audio_params = msg.get("audio_params") or {}
        try:
            sr = int(audio_params.get("sample_rate") or 16000)
            hub.mic_sample_rate = sr if sr > 0 else 16000
        except (TypeError, ValueError):
            hub.mic_sample_rate = 16000
        await hub.log("info", f"Device hello (mic {hub.mic_sample_rate} Hz)")
        await hub.send_device({"type": "config", "listen_ms": settings.listen_ms})
        await hub.broadcast({"type": "hello", "from": "device", "payload": msg})
    elif kind == "listen":
        state = msg.get("state")
        if state == "start":
            hub.start_listen()
            await hub.set_state("listening")
            await hub.log("info", f"Listen {settings.listen_ms}ms start")
            await hub.broadcast({"type": "listen", "state": "start", "ms": settings.listen_ms})
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
