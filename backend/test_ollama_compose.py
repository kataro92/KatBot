"""Ollama compose pass: question + search facts, history keeps the original question."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import COMPOSE_SYSTEM_PROMPT_VI, settings
from app.ollama_session import OllamaSession

settings.cursor_cli_enabled = False


def _check(cond: bool, name: str) -> int:
    if cond:
        print("PASS", name)
        return 0
    print("FAIL", name)
    return 1


async def _run() -> int:
    fail = 0
    session = OllamaSession()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "Hà Nội hôm nay 26 độ, trời mưa rào vừa nha."}
    }
    session._client.post = AsyncMock(return_value=mock_resp)

    question = "thời tiết hôm nay"
    facts = "- Thời tiết Hà Nội lúc 06:00: 26.1°C, mưa rào vừa"
    reply = await session.chat(question, web_context=facts, num_predict=240)

    fail += _check("26 độ" in reply, "compose reply")
    payload = session._client.post.call_args.kwargs["json"]
    sent = payload["messages"][-1]["content"]
    fail += _check(payload["model"] == settings.ollama_compose_model, "uses local compose model")
    fail += _check(payload.get("think") is False, "think disabled for compose")
    fail += _check(payload["messages"][0]["content"] == COMPOSE_SYSTEM_PROMPT_VI, "compose system prompt")
    fail += _check("Câu hỏi của người dùng" in sent, "payload has question label")
    fail += _check(question in sent, "payload has original question")
    fail += _check("26.1°C" in sent, "payload has search facts")
    fail += _check("Thông tin đã tìm được" in sent, "payload has facts label")
    fail += _check(payload["options"]["num_predict"] == 240, "num_predict tools")
    fail += _check(session._messages[-2]["content"] == question, "history stores original question")
    fail += _check("Thông tin đã tìm được" not in session._messages[-2]["content"], "history omits search dump")
    fail += _check(session._messages[-1]["role"] == "assistant", "history stores assistant")
    await session.close()
    return fail


def main() -> int:
    fail = asyncio.run(_run())
    if fail:
        print(f"{fail} failed")
        return 1
    print("All compose tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
