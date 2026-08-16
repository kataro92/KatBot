"""Shared turn: user text (typed or STT) → chat UI + Ollama → TTS on ESP speaker."""

from __future__ import annotations

import asyncio
import logging

from .hub import hub
from .ollama_session import OllamaError, OllamaSession
from .stt import transcribe
from .tts import PLAY_HZ, synth_pcm16

log = logging.getLogger("meobot.pipeline")

_lock = asyncio.Lock()
PCM_CHUNK = 1024  # bytes; keep under WebSockets 2KB cap
PREFILL_CHUNKS = 4  # ~128 ms so ESP ring is primed before realtime pacing


async def handle_user_text(session: OllamaSession, text: str) -> str:
    user = (text or "").strip()
    if not user:
        return ""
    async with _lock:
        await hub.broadcast({"type": "chat", "role": "user", "text": user})
        try:
            reply = await session.chat(user)
        except OllamaError as exc:
            await hub.log("error", f"Ollama: {exc}")
            await hub.send_device({"type": "state", "value": "idle"})
            await hub.set_state("idle")
            return ""
        await hub.broadcast({"type": "chat", "role": "assistant", "text": reply})
        await _speak(reply)
        return reply


async def _speak(reply: str) -> None:
    if not reply or not hub.device_online:
        await hub.set_state("idle")
        await hub.send_device({"type": "state", "value": "idle"})
        return
    await hub.set_state("speaking")
    await hub.send_device({"type": "tts", "state": "start"})
    await hub.send_device({"type": "tts", "state": "sentence_start", "text": reply[:80]})
    try:
        pcm = await asyncio.to_thread(synth_pcm16, reply)
    except Exception as exc:
        log.exception("TTS failed")
        await hub.log("error", f"TTS loi: {exc}")
        pcm = b""
    # Realtime pacing after a short prefill. 0.85x used to overrun the 32 ms ring → drop/crackle.
    pace = PCM_CHUNK / (PLAY_HZ * 2)
    n = 0
    for i in range(0, len(pcm), PCM_CHUNK):
        await hub.send_device_bin(pcm[i : i + PCM_CHUNK])
        n += 1
        if n >= PREFILL_CHUNKS:
            await asyncio.sleep(pace)
    await asyncio.sleep(PREFILL_CHUNKS * pace + 0.06)
    await hub.send_device({"type": "tts", "state": "stop"})
    await hub.set_state("idle")


async def on_listen_stop(session: OllamaSession) -> None:
    pcm = hub.stop_listen()
    await hub.set_state("thinking")
    await hub.log("info", f"Listen ended, {len(pcm)} bytes PCM")
    if len(pcm) < 4000:
        await hub.log("warn", "Mic qua ngan / khong co PCM")
        await hub.send_device({"type": "state", "value": "idle"})
        await hub.set_state("idle")
        return
    try:
        text = await asyncio.to_thread(transcribe, pcm, 8000)
    except Exception as exc:
        log.exception("STT failed")
        await hub.log("error", f"STT loi: {exc}")
        await hub.send_device({"type": "state", "value": "idle"})
        await hub.set_state("idle")
        return
    if not text:
        await hub.log("warn", "STT trong")
        await hub.send_device({"type": "state", "value": "idle"})
        await hub.set_state("idle")
        return
    await hub.log("info", f"STT: {text}")
    await handle_user_text(session, text)
