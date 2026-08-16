from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

import httpx

from .config import SYSTEM_PROMPT_VI, settings

log = logging.getLogger("meobot.ollama")

KEEP_TURNS = 4  # user+assistant pairs besides system


class OllamaError(RuntimeError):
    pass


class OllamaSession:
    """One warm chat session reused for the device and the monitor test box."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0))
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT_VI}
        ]
        self.ready = False
        self.last_error: str | None = None

    def reset(self) -> None:
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT_VI}]

    def _trim(self) -> None:
        extra = self._messages[1:]
        keep = KEEP_TURNS * 2
        if len(extra) > keep:
            self._messages = [self._messages[0]] + extra[-keep:]

    async def close(self) -> None:
        await self._client.aclose()

    def _keep_alive(self) -> Any:
        raw = settings.ollama_keep_alive
        if raw == "-1":
            return -1
        try:
            return int(raw)
        except ValueError:
            return raw

    async def warmup(self) -> None:
        url = f"{settings.ollama_host.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_VI},
                {"role": "user", "content": "ping"},
            ],
            "stream": False,
            "keep_alive": self._keep_alive(),
            "options": {"num_predict": 8},
        }
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                r = await self._client.post(url, json=payload)
                if r.status_code >= 500 and attempt < 2:
                    log.warning("Ollama warmup %s, retry %s", r.status_code, attempt + 1)
                    await asyncio.sleep(2)
                    continue
                r.raise_for_status()
                self.ready = True
                self.last_error = None
                log.info("Ollama warmup ok model=%s", settings.ollama_model)
                return
            except Exception as exc:
                last_exc = exc
                log.warning("Ollama warmup attempt %s failed: %s", attempt + 1, exc)
                await asyncio.sleep(2)
        self.ready = False
        self.last_error = str(last_exc)
        log.exception("Ollama warmup failed")
        raise OllamaError(f"Ollama warmup failed: {last_exc}") from last_exc

    async def chat(self, user_text: str) -> str:
        text = (user_text or "").strip()
        if not text:
            return ""
        self._messages.append({"role": "user", "content": text})
        self._trim()
        url = f"{settings.ollama_host.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_model,
            "messages": self._messages,
            "stream": False,
            "keep_alive": self._keep_alive(),
            "options": {
                "num_predict": settings.ollama_num_predict,
                "temperature": 0.7,
            },
        }
        try:
            r = await self._client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            reply = (data.get("message") or {}).get("content") or ""
            reply = reply.strip()
            self._messages.append({"role": "assistant", "content": reply})
            self._trim()
            self.ready = True
            self.last_error = None
            return reply
        except Exception as exc:
            if self._messages and self._messages[-1]["role"] == "user":
                self._messages.pop()
            self.last_error = str(exc)
            log.exception("Ollama chat failed")
            raise OllamaError(str(exc)) from exc

    async def chat_stream(self, user_text: str) -> AsyncIterator[str]:
        """Yield token deltas; caller concatenates. Used in later TTS-pipeline stages."""
        text = (user_text or "").strip()
        if not text:
            return
        self._messages.append({"role": "user", "content": text})
        self._trim()
        url = f"{settings.ollama_host.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_model,
            "messages": self._messages,
            "stream": True,
            "keep_alive": self._keep_alive(),
            "options": {
                "num_predict": settings.ollama_num_predict,
                "temperature": 0.7,
            },
        }
        pieces: list[str] = []
        try:
            async with self._client.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    import json

                    data = json.loads(line)
                    delta = (data.get("message") or {}).get("content") or ""
                    if delta:
                        pieces.append(delta)
                        yield delta
                    if data.get("done"):
                        break
            reply = "".join(pieces).strip()
            self._messages.append({"role": "assistant", "content": reply})
            self._trim()
        except Exception as exc:
            if self._messages and self._messages[-1]["role"] == "user":
                self._messages.pop()
            self.last_error = str(exc)
            raise OllamaError(str(exc)) from exc
