from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import WebSocket

from .config import settings
from .store import db

log = logging.getLogger("meobot.hub")


class Hub:
    """One ESP-12F device socket + many monitor browsers. Monitors never talk to the chip."""

    def __init__(self) -> None:
        self.device: WebSocket | None = None
        self.session_id: str | None = None
        self.monitors: set[WebSocket] = set()
        self.device_online = False
        self.state = "offline"
        self.temp: float | None = None
        self.humidity: float | None = None
        self.listen_ms: int | None = None
        self.mic_sample_rate: int = 16000  # updated from hello audio_params
        self.listen_chunks: int = 0
        self.audio = bytearray()
        self.listening = False
        self.mic_source = "esp"  # esp | pc
        self.speaker = "esp"  # esp | pc
        self.esp_volume = 80  # 0..100
        self.fw_version: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "device_online": self.device_online,
            "state": self.state,
            "temp": self.temp,
            "humidity": self.humidity,
            "session_id": self.session_id,
            "listen_ms": self.listen_ms,
            "listen_duration_ms": settings.listen_ms,
            "mic_source": self.mic_source,
            "speaker": self.speaker,
            "esp_volume": self.esp_volume,
            "fw_version": self.fw_version,
        }

    async def attach_device(self, ws: WebSocket) -> str:
        if self.device is not None:
            try:
                await self.device.close()
            except Exception:
                pass
        self.device = ws
        self.device_online = True
        self.session_id = uuid.uuid4().hex[:12]
        self.state = "idle"
        await self.broadcast(self.snapshot())
        await self.log("info", "ESP-12F connected")
        return self.session_id

    async def detach_device(self, ws: WebSocket) -> None:
        if self.device is ws:
            self.device = None
            self.device_online = False
            self.state = "offline"
            self.listening = False
            self.session_id = None
            self.fw_version = None
            await self.broadcast(self.snapshot())
            await self.log("warn", "ESP-12F disconnected")

    async def attach_monitor(self, ws: WebSocket) -> None:
        self.monitors.add(ws)
        await ws.send_text(json.dumps(self.snapshot(), ensure_ascii=False))

    def detach_monitor(self, ws: WebSocket) -> None:
        self.monitors.discard(ws)

    async def send_device(self, msg: dict[str, Any]) -> None:
        if self.device is None:
            return
        try:
            await self.device.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            log.exception("send_device failed")

    async def send_device_bin(self, data: bytes) -> None:
        if self.device is None or not data:
            return
        try:
            await self.device.send_bytes(data)
        except Exception:
            log.exception("send_device_bin failed")

    async def broadcast(self, msg: dict[str, Any]) -> None:
        if "ts" not in msg:
            msg["ts"] = int(time.time() * 1000)
        try:
            await asyncio.to_thread(self._persist, msg)
        except Exception:
            log.exception("persist failed")
        dead: list[WebSocket] = []
        payload = json.dumps(msg, ensure_ascii=False)
        for ws in self.monitors:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.monitors.discard(ws)

    def _persist(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        ts = int(msg.get("ts") or time.time() * 1000)
        if kind == "chat":
            db().insert_chat(
                ts,
                str(msg.get("role") or ""),
                str(msg.get("text") or ""),
                msg.get("audio_id"),
            )
        elif kind == "log":
            level = str(msg.get("level") or "info")
            db().insert_log(ts, level, str(msg.get("message") or ""))
        elif kind == "telemetry":
            temp = msg.get("temp")
            humidity = msg.get("humidity")
            try:
                temp_f = float(temp) if temp is not None else None
            except (TypeError, ValueError):
                temp_f = None
            try:
                hum_f = float(humidity) if humidity is not None else None
            except (TypeError, ValueError):
                hum_f = None
            db().insert_telemetry(
                ts,
                temp_f,
                hum_f,
                str(msg.get("state") or self.state or ""),
                self.device_online,
                self.session_id,
            )

    async def log(self, level: str, message: str) -> None:
        await self.broadcast({"type": "log", "level": level, "message": message})

    async def set_state(self, state: str) -> None:
        self.state = state
        await self.broadcast({"type": "state", "state": state})

    def start_listen(self) -> None:
        self.audio.clear()
        self.listening = True
        self.listen_ms = settings.listen_ms
        self.listen_chunks = 0

    def add_audio(self, data: bytes) -> None:
        if self.listening:
            self.audio.extend(data)
            self.listen_chunks += 1

    def stop_listen(self) -> bytes:
        self.listening = False
        self.listen_ms = None
        data = bytes(self.audio)
        self.audio.clear()
        return data

    async def set_audio_route(
        self,
        *,
        mic: str | None = None,
        speaker: str | None = None,
        esp_volume: int | None = None,
    ) -> dict[str, str | int]:
        prev = (self.mic_source, self.speaker, self.esp_volume)
        if mic in ("esp", "pc"):
            self.mic_source = mic
        if speaker in ("esp", "pc"):
            self.speaker = speaker
        if esp_volume is not None:
            self.esp_volume = max(0, min(100, int(esp_volume)))
        route: dict[str, str | int] = {
            "mic_source": self.mic_source,
            "speaker": self.speaker,
            "esp_volume": self.esp_volume,
        }
        if prev != (self.mic_source, self.speaker, self.esp_volume):
            await self.broadcast({"type": "audio_route", **route})
        return route


hub = Hub()
