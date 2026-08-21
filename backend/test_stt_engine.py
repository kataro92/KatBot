"""STT engine selection: PhoWhisper, faster-whisper, ElevenLabs."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import stt as stt_mod
from app.config import settings
from app.stt import stt_engine_name, _whisper_model_id, _eleven_language


def _check(cond: bool, name: str) -> int:
    if cond:
        print("PASS", name)
        return 0
    print("FAIL", name)
    return 1


class _FakeResp:
    status_code = 200
    text = ""

    def json(self):
        return {"text": "xin chao"}


class _FakeClient:
    last = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, data=None, files=None):
        _FakeClient.last = {
            "url": url,
            "headers": headers,
            "data": data,
            "files": files,
        }
        return _FakeResp()


def main() -> int:
    fail = 0
    prev_engine = settings.stt_engine
    prev_model = settings.whisper_model
    prev_key = settings.elevenlabs_api_key
    prev_stt_model = settings.elevenlabs_stt_model
    prev_lang = settings.stt_language
    prev_loaded = stt_mod._model
    prev_label = stt_mod._model_label
    try:
        settings.stt_engine = "phowhisper"
        fail += _check(stt_engine_name() == "phowhisper", "engine phowhisper")
        settings.stt_engine = "faster-whisper"
        fail += _check(stt_engine_name() == "faster-whisper", "engine faster-whisper")
        settings.stt_engine = "faster_whisper"
        fail += _check(stt_engine_name() == "faster-whisper", "engine underscore alias")
        settings.stt_engine = "systran"
        fail += _check(stt_engine_name() == "faster-whisper", "engine systran alias")
        settings.stt_engine = "elevenlabs"
        fail += _check(stt_engine_name() == "elevenlabs", "engine elevenlabs")
        settings.stt_engine = "scribe"
        fail += _check(stt_engine_name() == "elevenlabs", "engine scribe alias")
        settings.stt_engine = "11labs"
        fail += _check(stt_engine_name() == "elevenlabs", "engine 11labs alias")
        settings.stt_engine = "nope"
        try:
            stt_engine_name()
            fail += _check(False, "engine invalid")
        except ValueError as exc:
            fail += _check("elevenlabs" in str(exc), "engine invalid")

        settings.whisper_model = "large"
        fail += _check(_whisper_model_id() == "large-v3", "whisper large alias")
        settings.whisper_model = "small"
        fail += _check(_whisper_model_id() == "small", "whisper small")
        settings.whisper_model = "Systran/faster-whisper-small"
        fail += _check(_whisper_model_id() == "Systran/faster-whisper-small", "whisper hub id")

        settings.stt_language = "vi"
        fail += _check(_eleven_language() == "vie", "eleven language vi->vie")
        settings.stt_language = "vie"
        fail += _check(_eleven_language() == "vie", "eleven language vie")

        settings.stt_engine = "elevenlabs"
        settings.elevenlabs_api_key = ""
        stt_mod._model = None
        try:
            stt_mod._get_model()
            fail += _check(False, "eleven missing key")
        except RuntimeError:
            fail += _check(True, "eleven missing key")

        settings.elevenlabs_api_key = "test-key"
        settings.elevenlabs_stt_model = "scribe_v2"
        settings.stt_language = "vi"
        pcm = b"\x00\x00" * 2500
        fail += _check(stt_mod.transcribe(b"\x00\x00" * 100) == "", "eleven short pcm skip")
        with patch.object(httpx, "Client", _FakeClient):
            text = stt_mod.transcribe(pcm, 8000)
        fail += _check(text == "xin chao", "eleven transcribe mock")
        posted = _FakeClient.last or {}
        fail += _check(
            posted.get("url") == "https://api.elevenlabs.io/v1/speech-to-text",
            "eleven post url",
        )
        fail += _check((posted.get("data") or {}).get("language_code") == "vie", "eleven post lang")
        fail += _check(
            (posted.get("data") or {}).get("file_format") == "pcm_s16le_16",
            "eleven post pcm format",
        )
        fail += _check(
            (posted.get("headers") or {}).get("xi-api-key") == "test-key",
            "eleven post key header",
        )

        quiet = (np.array([80, -60, 40, -90] * 20, dtype=np.int16)).tobytes()
        boosted, gain, peak_in, peak_out = stt_mod.prepare_stt_pcm(quiet)
        fail += _check(gain > 2.0 and peak_out > peak_in, "prepare_stt_pcm boosts quiet")
        fail += _check(len(boosted) == len(quiet), "prepare_stt_pcm length")
        silent = b"\x00\x00" * 16
        _, g0, p0, _ = stt_mod.prepare_stt_pcm(silent)
        fail += _check(g0 == 1.0 and p0 == 0, "prepare_stt_pcm silence")
    finally:
        settings.stt_engine = prev_engine
        settings.whisper_model = prev_model
        settings.elevenlabs_api_key = prev_key
        settings.elevenlabs_stt_model = prev_stt_model
        settings.stt_language = prev_lang
        stt_mod._model = prev_loaded
        stt_mod._model_label = prev_label

    from faster_whisper import WhisperModel  # noqa: F401

    fail += _check(True, "import faster_whisper")
    if fail:
        print(f"{fail} failed")
        return 1
    print("All STT engine tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
