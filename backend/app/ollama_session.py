from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

import httpx

from .config import settings
from .context import build_system_prompt

log = logging.getLogger("meobot.ollama")

KEEP_TURNS = 4  # user+assistant pairs besides system


class OllamaError(RuntimeError):
    pass


class OllamaSession:
    """One warm chat session reused for the device and the monitor test box."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0))
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": build_system_prompt()}
        ]
        self.ready = False
        self.last_error: str | None = None
        self.cursor_ready = False
        self.cursor_error: str | None = None
        self.last_backend: str | None = None
        self._cursor_sid: str | None = None

    def reset(self) -> None:
        self._messages = [{"role": "system", "content": build_system_prompt()}]

    def _sync_system(self) -> None:
        if not self._messages or self._messages[0]["role"] != "system":
            self._messages.insert(0, {"role": "system", "content": build_system_prompt()})
        else:
            self._messages[0]["content"] = build_system_prompt()

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
                {"role": "system", "content": build_system_prompt()},
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

    async def chat(
        self,
        user_text: str,
        *,
        web_context: str | None = None,
        num_predict: int | None = None,
    ) -> str:
        text = (user_text or "").strip()
        if not text:
            return ""
        self._sync_system()
        if settings.cursor_cli_enabled:
            try:
                reply = await self._chat_cursor(text, web_context)
                if reply:
                    return reply
            except Exception as exc:
                log.warning("Cursor CLI failed, fallback Ollama: %s", exc)
                self.cursor_error = str(exc)
        if web_context and web_context.strip():
            return await self._compose_from_search(text, web_context, num_predict)
        return await self._chat_plain(text, num_predict)

    def _cursor_prompt(self, text: str, web_context: str | None) -> str:
        if web_context and web_context.strip():
            from .config import COMPOSE_SYSTEM_PROMPT_VI
            from .context import compose_from_facts

            return (
                f"{COMPOSE_SYSTEM_PROMPT_VI}\n\n"
                f"{compose_from_facts(text, web_context)}"
            )
        lines = [build_system_prompt()]
        for msg in self._messages[1:]:
            role = "Người dùng" if msg.get("role") == "user" else "Mèo"
            lines.append(f"{role}: {msg.get('content') or ''}")
        lines.append(f"Người dùng: {text}")
        lines.append("Chỉ nói câu trả lời. Không dùng tool, không đọc file, không sửa code.")
        return "\n".join(lines)

    async def _chat_cursor(self, text: str, web_context: str | None) -> str:
        from .cursor_cli import CursorCliError, ask_cursor_sync

        prompt = self._cursor_prompt(text, web_context)
        try:
            reply, sid = await asyncio.to_thread(
                ask_cursor_sync, prompt, resume_id=self._cursor_sid
            )
        except CursorCliError:
            if not self._cursor_sid:
                raise
            log.info("Cursor resume failed, starting a new CLI session")
            reply, sid = await asyncio.to_thread(ask_cursor_sync, prompt, resume_id=None)
        if not reply:
            raise CursorCliError("Cursor CLI result rong")
        if sid:
            self._cursor_sid = sid
        self.cursor_ready = True
        self.cursor_error = None
        self.last_backend = f"cursor:{settings.cursor_cli_model or 'auto'}"
        self._remember(text, reply)
        log.info("Reply via Cursor CLI model=%s", settings.cursor_cli_model or "auto")
        return reply

    async def _chat_plain(self, text: str, num_predict: int | None) -> str:
        request_messages = self._messages + [{"role": "user", "content": text}]
        reply = await self._post_chat(
            settings.ollama_model,
            request_messages,
            num_predict=num_predict or settings.ollama_num_predict,
            temperature=0.7,
        )
        self.last_backend = f"ollama:{settings.ollama_model}"
        self._remember(text, reply)
        return reply

    async def _compose_from_search(
        self,
        text: str,
        facts: str,
        num_predict: int | None,
    ) -> str:
        from .config import COMPOSE_SYSTEM_PROMPT_VI
        from .context import compose_from_facts

        model = (settings.ollama_compose_model or settings.ollama_model).strip()
        request_messages = [
            {"role": "system", "content": COMPOSE_SYSTEM_PROMPT_VI},
            {"role": "user", "content": compose_from_facts(text, facts)},
        ]
        log.info("Compose via local Ollama model=%s", model)
        reply = await self._post_chat(
            model,
            request_messages,
            num_predict=num_predict or settings.ollama_num_predict_tools,
            temperature=0.5,
            think=False,
        )
        if not reply:
            return ""
        self.last_backend = f"ollama:{model}"
        self._remember(text, reply)
        return reply

    def _remember(self, user_text: str, reply: str) -> None:
        self._messages.append({"role": "user", "content": user_text})
        self._messages.append({"role": "assistant", "content": reply or "(trong)"})
        self._trim()
        self.ready = True
        self.last_error = None

    async def _post_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        num_predict: int,
        temperature: float,
        think: bool | None = None,
    ) -> str:
        url = f"{settings.ollama_host.rstrip('/')}/api/chat"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": self._keep_alive(),
            "options": {
                "num_predict": num_predict,
                "temperature": temperature,
            },
        }
        if think is False:
            payload["think"] = False
        try:
            r = await self._client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            msg = data.get("message") or {}
            reply = (msg.get("content") or data.get("response") or "").strip()
            if not reply:
                log.warning(
                    "Ollama empty reply model=%s status=%s keys=%s",
                    model,
                    r.status_code,
                    list(data.keys()),
                )
            return reply
        except Exception as exc:
            self.last_error = str(exc)
            log.exception("Ollama chat failed model=%s", model)
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
