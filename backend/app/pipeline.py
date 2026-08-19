"""Shared turn: user text (typed or STT) → chat UI + Ollama → TTS on ESP speaker."""

from __future__ import annotations

import asyncio
import logging

from .clips import put_pcm
from .hub import hub
from .ollama_session import OllamaError, OllamaSession
from .stt import transcribe
from .tts import PLAY_HZ, synth_pcm16
from .config import settings
from .tools import run_tools

log = logging.getLogger("meobot.pipeline")

_lock = asyncio.Lock()
PCM_CHUNK = 1024  # bytes; keep under WebSockets 2KB cap
PREFILL_CHUNKS = 4  # ~128 ms so ESP ring is primed before realtime pacing


async def handle_user_text(
    session: OllamaSession,
    text: str,
    *,
    audio_id: str | None = None,
) -> str:
    user = (text or "").strip()
    if not user:
        return ""
    async with _lock:
        user_msg: dict = {"type": "chat", "role": "user", "text": user}
        if audio_id:
            user_msg["audio_id"] = audio_id
        await hub.broadcast(user_msg)
        try:
            tool = await asyncio.to_thread(
                run_tools, user, search_enabled=settings.web_search_enabled
            )
        except Exception as exc:
            log.warning("Tool failed: %s", exc)
            await hub.log("warn", f"Tool loi: {exc}")
            tool = None
        if tool and tool.kind != "none":
            await hub.log("info", f"Tool {tool.kind}")
        if tool and tool.kind == "music":
            intro = tool.spoken or "Đang phát nhạc"
            await hub.broadcast({"type": "chat", "role": "assistant", "text": intro})
            await _speak(intro)
            if tool.music_pcm:
                await _play_pcm(tool.music_pcm)
            else:
                await hub.set_state("idle")
                await hub.send_device({"type": "state", "value": "idle"})
            return intro
        web_ctx = tool.context if tool else None
        predict = (
            settings.ollama_num_predict_tools
            if web_ctx
            else settings.ollama_num_predict
        )
        if web_ctx:
            await hub.log(
                "info",
                f"Compose {tool.kind} via Cursor Auto, fallback {settings.ollama_compose_model or settings.ollama_model}",
            )
        reply = ""
        try:
            reply = await session.chat(user, web_context=web_ctx, num_predict=predict)
            if session.last_backend:
                await hub.log("info", f"LLM {session.last_backend}")
        except OllamaError as exc:
            await hub.log("error", f"Ollama: {exc}")
            reply = ""
        if not reply:
            reply = (tool.spoken if tool else None) or "Mình chưa trả lời được, hỏi lại giúp mình nhé."
            await hub.log("warn", "Ollama trong, dung cau tra loi tool")
        await hub.broadcast({"type": "chat", "role": "assistant", "text": reply})
        await _speak(reply)
        return reply


async def _speak(reply: str) -> None:
    if not reply:
        await hub.set_state("idle")
        await hub.send_device({"type": "state", "value": "idle"})
        return
    if not hub.device_online:
        await hub.set_state("idle")
        return
    try:
        pcm = await asyncio.to_thread(synth_pcm16, reply)
    except Exception as exc:
        log.exception("TTS failed")
        await hub.log("error", f"TTS loi: {exc}")
        await hub.set_state("idle")
        await hub.send_device({"type": "state", "value": "idle"})
        return
    await _play_pcm(pcm, caption=reply[:80])


async def _play_pcm(pcm: bytes, caption: str = "") -> None:
    if not pcm or not hub.device_online:
        await hub.set_state("idle")
        await hub.send_device({"type": "state", "value": "idle"})
        return
    await hub.set_state("speaking")
    await hub.send_device({"type": "tts", "state": "start"})
    if caption:
        await hub.send_device({"type": "tts", "state": "sentence_start", "text": caption})
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
    mic_hz = hub.mic_sample_rate
    try:
        text = await asyncio.to_thread(transcribe, pcm, mic_hz)
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
    audio_id = put_pcm(pcm, mic_hz)
    await handle_user_text(session, text, audio_id=audio_id)
