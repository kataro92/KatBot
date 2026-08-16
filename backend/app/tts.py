from __future__ import annotations

import io
import logging

import numpy as np
from gtts import gTTS

from .config import settings

log = logging.getLogger("meobot.tts")

PLAY_HZ = 16000
# EnvChatBot AudioOutputI2S SetGain ~0.85 + soft limit — full-scale PCM clip trên MAX98357.
SPEECH_GAIN = 0.82
FADE_MS = 14
SOFT_LIMIT = 24000


def prepare_playback(pcm: bytes) -> bytes:
    """DC remove, headroom, fade — bớt rè/click khi I2S start/stop."""
    if len(pcm) < 4:
        return pcm
    x = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype=np.int16).astype(np.float32)
    if x.size == 0:
        return b""
    x -= float(x.mean())
    peak = float(np.max(np.abs(x))) or 1.0
    x *= min(1.0, (32767.0 * SPEECH_GAIN) / peak)
    x = np.tanh(x / float(SOFT_LIMIT)) * float(SOFT_LIMIT)
    fade = min(int(PLAY_HZ * FADE_MS / 1000), max(1, x.size // 6))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        x[:fade] *= ramp
        x[-fade:] *= ramp[::-1]
    return np.clip(x, -32767, 32767).astype(np.int16).tobytes()


def synth_pcm16(text: str) -> bytes:
    """Return 16 kHz mono signed-16 PCM for the ESP I2S amp."""
    clean = (text or "").strip()
    if not clean:
        return b""
    buf = io.BytesIO()
    gTTS(text=clean, lang=settings.gtts_lang, tld=settings.gtts_tld).write_to_fp(buf)
    mp3 = buf.getvalue()
    import miniaudio

    decoded = miniaudio.decode(
        mp3,
        nchannels=1,
        sample_rate=PLAY_HZ,
        output_format=miniaudio.SampleFormat.SIGNED16,
    )
    return prepare_playback(bytes(decoded.samples))
