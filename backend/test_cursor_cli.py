"""Cursor CLI command building, JSON parse, and Ollama fallback."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.cursor_cli import CursorCliError, _parse_print_json, find_agent_argv
from app.ollama_session import OllamaSession


def _check(cond: bool, name: str) -> int:
    if cond:
        print("PASS", name)
        return 0
    print("FAIL", name)
    return 1


def test_parse() -> int:
    fail = 0
    text, sid = _parse_print_json(
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "meo",
                "session_id": "abc",
            }
        )
    )
    fail += _check(text == "meo" and sid == "abc", "parse json result")
    try:
        _parse_print_json(json.dumps({"is_error": True, "result": "nope"}))
        fail += _check(False, "parse is_error")
    except CursorCliError:
        fail += _check(True, "parse is_error")
    fail += _check(_parse_print_json("chi la text")[0] == "chi la text", "parse plain text")
    return fail


def test_find_agent() -> int:
    argv = find_agent_argv()
    joined = " ".join(argv).lower()
    ok = any(p.endswith("index.js") or p.endswith("agent.cmd") or "agent" in p.lower() for p in argv)
    print("agent argv", argv)
    return _check(ok and ("node" in joined or "agent" in joined), "find local Cursor CLI")


async def _fallback_and_cursor() -> int:
    fail = 0
    prev = settings.cursor_cli_enabled
    settings.cursor_cli_enabled = True
    try:
        session = OllamaSession()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "ollama-ok"}}
        session._client.post = AsyncMock(return_value=mock_resp)

        with patch("app.cursor_cli.ask_cursor_sync", side_effect=CursorCliError("cli down")):
            reply = await session.chat("xin chao")
        fail += _check(reply == "ollama-ok", "fallback to ollama")
        fail += _check(session.last_backend.startswith("ollama:"), "last_backend ollama")
        fail += _check(session._client.post.await_count == 1, "ollama called after cli error")
        await session.close()

        session = OllamaSession()
        session._client.post = AsyncMock(return_value=mock_resp)
        with patch("app.cursor_cli.ask_cursor_sync", return_value=("meo", "sid-1")):
            reply = await session.chat("xin chao")
        fail += _check(reply == "meo", "cursor reply")
        fail += _check(session.last_backend.startswith("cursor:"), "last_backend cursor")
        fail += _check(session._cursor_sid == "sid-1", "stores cursor session")
        fail += _check(session._client.post.await_count == 0, "ollama skipped when cursor ok")
        await session.close()
    finally:
        settings.cursor_cli_enabled = prev
    return fail


def main() -> int:
    fail = 0
    fail += test_parse()
    fail += test_find_agent()
    fail += asyncio.run(_fallback_and_cursor())
    if fail:
        print(f"{fail} failed")
        return 1
    print("All cursor CLI tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
