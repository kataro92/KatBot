from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

from .config import settings

log = logging.getLogger("meobot.stt")

_model = None
_model_label = ""

_CT2_REPO = "quocphu/PhoWhisper-ct2-FasterWhisper"
_CT2_FOLDERS = {
    "tiny": "PhoWhisper-tiny-ct2-fasterWhisper",
    "base": "PhoWhisper-base-ct2-fasterWhisper",
    "small": "PhoWhisper-small-ct2-fasterWhisper",
    "medium": "PhoWhisper-medium-ct2-fasterWhisper",
    "large": "PhoWhisper-large-ct2-fasterWhisper",
    "vinai/phowhisper-tiny": "PhoWhisper-tiny-ct2-fasterWhisper",
    "vinai/phowhisper-base": "PhoWhisper-base-ct2-fasterWhisper",
    "vinai/phowhisper-small": "PhoWhisper-small-ct2-fasterWhisper",
    "vinai/phowhisper-medium": "PhoWhisper-medium-ct2-fasterWhisper",
    "vinai/phowhisper-large": "PhoWhisper-large-ct2-fasterWhisper",
}


def _cpu_threads() -> int:
    n = settings.stt_cpu_threads
    if n > 0:
        return n
    logical = os.cpu_count() or 4
    # Physical cores: HT often slows CTranslate2. Ryzen 5 5500 = 6c/12t → 6.
    return max(1, logical // 2)


def _cuda_vram_mb() -> int:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            return 0
    except Exception:
        return 0
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        )
        return int(out.strip().splitlines()[0].split()[0])
    except Exception:
        return 0


def _pick_device() -> str:
    want = (settings.stt_device or "auto").strip().lower()
    if want in {"cpu", "cuda"}:
        return want
    # Quadro P400 2GB is slower than Ryzen 5 5500 for Whisper. Need ≥4 GB VRAM.
    return "cuda" if _cuda_vram_mb() >= 4096 else "cpu"


def _pick_compute(device: str) -> str:
    want = (settings.stt_compute_type or "auto").strip().lower()
    try:
        import ctranslate2

        supported = set(ctranslate2.get_supported_compute_types(device))
    except Exception:
        supported = {"float32", "int8"}
    if want != "auto":
        if want in supported:
            return want
        log.warning("STT compute %s not supported on %s, falling back", want, device)
    # Same WER as official Whisper in practice; much faster than float32.
    # Prefer int8_float32 (int8 weights, float32 math) over plain int8.
    for cand in ("int8_float32", "int8", "float16", "float32"):
        if cand in supported:
            return cand
    return "float32"


_PHOWHISPER_ENGINES = {"phowhisper", "pho", "vinai"}
_FASTER_WHISPER_ENGINES = {
    "faster-whisper",
    "faster_whisper",
    "fasterwhisper",
    "systran",
    "whisper",
    "openai",
}
_WHISPER_SIZE_ALIASES = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large": "large-v3",
    "large-v1": "large-v1",
    "large-v2": "large-v2",
    "large-v3": "large-v3",
    "large-v3-turbo": "large-v3-turbo",
    "turbo": "turbo",
    "distil-large-v3": "distil-large-v3",
    "distil-large-v2": "distil-large-v2",
}


_ELEVENLABS_ENGINES = {"elevenlabs", "eleven", "11labs", "scribe"}
_LANG3 = {
    "vi": "vie",
    "en": "eng",
    "zh": "zho",
    "ja": "jpn",
    "ko": "kor",
    "fr": "fra",
    "de": "deu",
    "es": "spa",
}


def stt_engine_name() -> str:
    raw = (settings.stt_engine or "phowhisper").strip().lower().replace("_", "-")
    if raw in _PHOWHISPER_ENGINES:
        return "phowhisper"
    if raw in _FASTER_WHISPER_ENGINES:
        return "faster-whisper"
    if raw in _ELEVENLABS_ENGINES:
        return "elevenlabs"
    raise ValueError(
        "STT_ENGINE must be 'phowhisper', 'faster-whisper', or 'elevenlabs' "
        f"(got {settings.stt_engine!r})"
    )


def _whisper_model_id() -> str:
    raw = (settings.whisper_model or "small").strip()
    key = raw.lower().replace(" ", "")
    return _WHISPER_SIZE_ALIASES.get(key, raw)


def _phowhisper_size(name: str) -> str:
    key = name.strip().lower().replace(" ", "")
    for size in ("large", "medium", "small", "base", "tiny"):
        if key.endswith(size) or f"phowhisper-{size}" in key:
            return size
    return "medium"


def _phowhisper_ct2_path() -> str:
    raw = settings.phowhisper_model.strip()
    folder = _CT2_FOLDERS.get(raw.lower(), _CT2_FOLDERS[_phowhisper_size(raw)])
    from huggingface_hub import snapshot_download

    root = snapshot_download(
        _CT2_REPO,
        allow_patterns=[f"{folder}/*"],
    )
    path = Path(root) / folder
    if not (path / "model.bin").is_file():
        raise FileNotFoundError(f"PhoWhisper CT2 missing: {path}")
    return str(path)


def _load_whisper_model(device: str, compute: str):
    from faster_whisper import WhisperModel

    threads = _cpu_threads()
    engine = stt_engine_name()
    if engine == "phowhisper":
        model_path = _phowhisper_ct2_path()
        label = f"phowhisper:{Path(model_path).name}"
    else:
        model_path = _whisper_model_id()
        label = f"faster-whisper:{model_path}"
    log.info(
        "STT loading %s device=%s compute=%s threads=%s",
        label,
        device,
        compute,
        threads,
    )
    model = WhisperModel(
        model_path,
        device=device,
        compute_type=compute,
        cpu_threads=threads,
        num_workers=1,
    )
    return model, f"{label} {device}/{compute}"


def _get_model():
    global _model, _model_label
    if stt_engine_name() == "elevenlabs":
        key = (settings.elevenlabs_api_key or "").strip()
        if not key:
            raise RuntimeError("STT_ENGINE=elevenlabs can ELEVENLABS_API_KEY trong .env")
        label = f"elevenlabs:{settings.elevenlabs_stt_model or 'scribe_v2'}"
        if _model is not True:
            _model = True
            _model_label = label
            log.info("STT ready %s", _model_label)
        return _model
    if _model is not None:
        return _model
    device = _pick_device()
    compute = _pick_compute(device)
    try:
        _model, _model_label = _load_whisper_model(device, compute)
    except Exception as exc:
        if device != "cpu":
            log.warning("STT GPU failed (%s), using CPU", exc)
            compute = _pick_compute("cpu")
            _model, _model_label = _load_whisper_model("cpu", compute)
        else:
            raise
    log.info("STT ready %s", _model_label)
    return _model


def prepare_stt_pcm(pcm: bytes, *, target_peak: float = 10000.0, max_gain: float = 24.0) -> tuple[bytes, float, int, int]:
    """DC-remove and boost quiet INMP441 captures so Whisper sees speech.

    Returns (pcm, gain, peak_in, peak_out).
    """
    n = len(pcm) // 2
    if n == 0:
        return pcm, 1.0, 0, 0
    x = np.frombuffer(pcm[: n * 2], dtype=np.int16).astype(np.float32)
    x -= float(x.mean())
    peak_in = float(np.max(np.abs(x))) if x.size else 0.0
    if peak_in < 24.0:
        out = np.clip(x, -32767, 32767).astype(np.int16).tobytes()
        return out, 1.0, int(peak_in), int(peak_in)
    gain = min(max_gain, target_peak / peak_in)
    if gain < 1.05:
        gain = 1.0
    y = np.clip(x * gain, -32767, 32767).astype(np.int16)
    peak_out = int(np.max(np.abs(y.astype(np.int32))))
    return y.tobytes(), float(gain), int(peak_in), peak_out


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


def _pcm16_16k(pcm: bytes, in_hz: int) -> bytes:
    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return b""
    if in_hz == 16000:
        return pcm
    n_out = int(samples.size * 16000 / in_hz)
    x_old = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    out = np.interp(x_new, x_old, samples.astype(np.float32))
    return np.clip(out, -32768, 32767).astype(np.int16).tobytes()


def _eleven_language() -> str:
    raw = (settings.stt_language or "vi").strip().lower()
    if len(raw) == 3:
        return raw
    return _LANG3.get(raw, raw or "vie")


def _transcribe_elevenlabs(pcm: bytes, sample_rate: int) -> str:
    import httpx

    key = (settings.elevenlabs_api_key or "").strip()
    if not key:
        raise RuntimeError("Thieu ELEVENLABS_API_KEY")
    audio = _pcm16_16k(pcm, sample_rate)
    if len(audio) < 3200:
        return ""
    model_id = (settings.elevenlabs_stt_model or "scribe_v2").strip()
    with httpx.Client(timeout=httpx.Timeout(45.0, connect=8.0)) as client:
        r = client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": key},
            data={
                "model_id": model_id,
                "language_code": _eleven_language(),
                "file_format": "pcm_s16le_16",
                "tag_audio_events": "false",
                "temperature": "0",
            },
            files={"file": ("speech.pcm", audio, "application/octet-stream")},
        )
    if r.status_code >= 400:
        detail = (r.text or "").strip().replace("\n", " ")[:180]
        raise RuntimeError(f"ElevenLabs STT HTTP {r.status_code}: {detail}")
    data = r.json()
    return (data.get("text") or "").strip()


def transcribe(pcm: bytes, sample_rate: int = 16000) -> str:
    if len(pcm) < 4000:
        return ""
    if stt_engine_name() == "elevenlabs":
        _get_model()
        return _transcribe_elevenlabs(pcm, sample_rate)
    audio = pcm16_to_float(pcm, in_hz=sample_rate, out_hz=16000)
    if audio.size < 1600:
        return ""
    model = _get_model()
    lang = (settings.stt_language or "vi").strip() or "vi"
    segments, _info = model.transcribe(
        audio,
        language=lang,
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,
        without_timestamps=True,
        # Button listen is already a speech window. Silero VAD treated quiet
        # INMP441 / Vietnamese as silence and deleted the whole clip.
        vad_filter=False,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text
