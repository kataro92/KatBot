from __future__ import annotations

import logging

import numpy as np

from .config import settings

log = logging.getLogger("meobot.stt")

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        device = settings.stt_device
        if device == "auto":
            device = "cpu"
        _model = WhisperModel(settings.whisper_model, device=device, compute_type="int8")
        log.info("STT loaded model=%s device=%s", settings.whisper_model, device)
    return _model


def pcm16_to_float(pcm: bytes, in_hz: int = 8000, out_hz: int = 16000) -> np.ndarray:
    if len(pcm) < 2:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if in_hz == out_hz or samples.size == 0:
        return samples
    n_out = int(samples.size * out_hz / in_hz)
    x_old = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def transcribe(pcm: bytes, sample_rate: int = 8000) -> str:
    audio = pcm16_to_float(pcm, in_hz=sample_rate, out_hz=16000)
    if audio.size < 1600:
        return ""
    model = _get_model()
    segments, _info = model.transcribe(audio, language="vi", vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text
