"""Voice pipeline hooks. Phase 1: listen window only, no STT/TTS yet."""

from __future__ import annotations

import logging

from .hub import hub
from .ollama_session import OllamaSession

log = logging.getLogger("meobot.pipeline")


async def on_listen_stop(session: OllamaSession) -> None:
    pcm = hub.stop_listen()
    await hub.set_state("thinking")
    await hub.log("info", f"Listen ended, {len(pcm)} bytes PCM")

    if len(pcm) < 1600:
        # Phase 1: button+timer only, no mic stream yet.
        await hub.send_device({"type": "state", "value": "idle"})
        await hub.set_state("idle")
        return

    # Later stages: STT -> Ollama -> TTS streaming to device.
    _ = session
    await hub.send_device({"type": "state", "value": "idle"})
    await hub.set_state("idle")
