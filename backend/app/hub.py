from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import WebSocket

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
        self.audio = bytearray()
        self.listening = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "device_online": self.device_online,
            "state": self.state,
            "temp": self.temp,
            "humidity": self.humidity,
            "session_id": self.session_id,
            "listen_ms": self.listen_ms,
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

    async def broadcast(self, msg: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        payload = json.dumps(msg, ensure_ascii=False)
        for ws in self.monitors:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.monitors.discard(ws)

    async def log(self, level: str, message: str) -> None:
        await self.broadcast({"type": "log", "level": level, "message": message})

    async def set_state(self, state: str) -> None:
        self.state = state
        await self.broadcast({"type": "state", "state": state})

    def start_listen(self) -> None:
        self.audio.clear()
        self.listening = True
        self.listen_ms = 5000

    def add_audio(self, data: bytes) -> None:
        if self.listening:
            self.audio.extend(data)

    def stop_listen(self) -> bytes:
        self.listening = False
        self.listen_ms = None
        data = bytes(self.audio)
        self.audio.clear()
        return data


hub = Hub()
