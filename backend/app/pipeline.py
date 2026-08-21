"""Shared turn: user text (typed or STT) → chat UI + Ollama → TTS on ESP or PC speaker."""

from __future__ import annotations

import asyncio
import logging

from .clips import put_pcm
from .hub import hub
from .ollama_session import OllamaError, OllamaSession
from .stt import transcribe, prepare_stt_pcm
from .tts import PLAY_HZ, synth_pcm16
from .config import settings
from .tools import run_tools
import numpy as np

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
                await _go_idle()
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


async def _go_idle() -> None:
    await hub.set_state("idle")
    if hub.device_online:
        await hub.send_device({"type": "state", "value": "idle"})


async def _speak(reply: str) -> None:
    if not reply:
        await _go_idle()
        return
    dest = hub.speaker
    if dest == "esp" and not hub.device_online:
        await _go_idle()
        return
    try:
        pcm = await asyncio.to_thread(synth_pcm16, reply)
    except Exception as exc:
        log.exception("TTS failed")
        await hub.log("error", f"TTS loi: {exc}")
        await _go_idle()
        return
    await _play_pcm(pcm, caption=reply[:80])


async def _play_pcm(pcm: bytes, caption: str = "") -> None:
    if not pcm:
        await _go_idle()
        return
    dest = hub.speaker
    if dest == "pc":
        audio_id = put_pcm(pcm, PLAY_HZ)
        await hub.set_state("speaking")
        await hub.broadcast(
            {
                "type": "tts_play",
                "audio_id": audio_id,
                "caption": caption,
                "hz": PLAY_HZ,
            }
        )
        dur = len(pcm) / (PLAY_HZ * 2)
        await asyncio.sleep(min(max(dur, 0.2), 120.0))
        await _go_idle()
        return
    if not hub.device_online:
        await _go_idle()
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


def _mic_pcm_debug(pcm: bytes, hz: int, chunks: int, *, source: str = "esp") -> str:
    expect = max(1, int(settings.listen_ms * hz * 2 / 1000))
    n = len(pcm) // 2
    if n == 0:
        if source == "pc":
            return "mic PC trống (0 byte). Cho phép micro trình duyệt và nói trong cửa sổ nghe."
        return (
            f"mic PCM trống (0 byte, {chunks} khung WS). "
            f"Kỳ vọng ~{expect} byte / {settings.listen_ms} ms @ {hz} Hz. "
            "INMP441 SD phải vào D6 (GPIO12), SCK=D7, WS=D5 — không cắm SD vào RX."
        )
    samples = np.frombuffer(pcm[: n * 2], dtype=np.int16).astype(np.int32)
    peak = int(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    dur_ms = 1000.0 * n / max(hz, 1)
    if peak < 80:
        hint = " Peak gần 0: không có tiếng hoặc sai chân I2S RX."
        if source == "pc":
            hint = " Peak gần 0: nói gần mic máy tính hơn, kiểm tra quyền micro."
    elif peak < 500:
        hint = " Peak yếu: nói gần mic hơn."
        if source == "esp":
            hint += " Kiểm tra L/R=GND."
    else:
        hint = ""
    label = "mic PC" if source == "pc" else "mic PCM"
    return (
        f"{label} {len(pcm)} byte / {chunks} khung / {n} mẫu / {dur_ms:.0f} ms "
        f"@ {hz} Hz, peak={peak}, rms={rms:.0f}.{hint}"
    )


async def process_listen_pcm(
    session: OllamaSession,
    pcm: bytes,
    mic_hz: int,
    chunks: int,
    *,
    source: str = "esp",
) -> None:
    await hub.set_state("thinking")
    await hub.log("info", _mic_pcm_debug(pcm, mic_hz, chunks, source=source))
    if len(pcm) < 4000:
        await hub.log("warn", "Mic quá ngắn / không có PCM — bỏ qua STT")
        await _go_idle()
        return
    pcm, gain, peak_in, peak_out = prepare_stt_pcm(pcm)
    if gain > 1.2:
        await hub.log("info", f"mic boost x{gain:.1f} (peak {peak_in} → {peak_out})")
    try:
        text = await asyncio.to_thread(transcribe, pcm, mic_hz)
    except Exception as exc:
        log.exception("STT failed")
        await hub.log("error", f"STT loi: {exc}")
        await _go_idle()
        return
    if not text:
        await hub.log("warn", "STT trong")
        await _go_idle()
        return
    await hub.log("info", f"STT: {text}")
    audio_id = put_pcm(pcm, mic_hz)
    await handle_user_text(session, text, audio_id=audio_id)


async def on_listen_stop(session: OllamaSession) -> None:
    chunks = hub.listen_chunks
    pcm = hub.stop_listen()
    await process_listen_pcm(session, pcm, hub.mic_sample_rate, chunks, source="esp")
