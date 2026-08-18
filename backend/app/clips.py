"""In-memory mic clips for the monitor replay button."""

from __future__ import annotations

import io
import uuid
import wave
from collections import OrderedDict

_MAX_CLIPS = 24
_clips: OrderedDict[str, tuple[bytes, int]] = OrderedDict()


def put_pcm(pcm: bytes, sample_rate: int = 8000) -> str:
    cid = uuid.uuid4().hex[:12]
    _clips[cid] = (bytes(pcm), int(sample_rate))
    while len(_clips) > _MAX_CLIPS:
        _clips.popitem(last=False)
    return cid


def get_pcm(clip_id: str) -> tuple[bytes, int] | None:
    return _clips.get(clip_id)


def pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()
