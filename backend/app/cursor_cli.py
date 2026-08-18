"""Local Cursor CLI (agent) for chat. Ask mode, model Auto, no file edits."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from .config import ROOT_DIR, settings

log = logging.getLogger("meobot.cursor_cli")

_CREATE_NO_WINDOW = 0x08000000
_VERSION_DIR_RE = re.compile(
    r"^\d{4}\.\d{1,2}\.\d{1,2}(-\d{2}-\d{2}-\d{2})?-[a-f0-9]+$"
)


class CursorCliError(RuntimeError):
    pass


def workspace_dir() -> Path:
    path = ROOT_DIR / ".cursor-cli-ws"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _version_key(name: str) -> tuple[int, str]:
    date = name.split("-")[0]
    parts = date.split(".")
    if len(parts) != 3:
        return (0, name)
    try:
        y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return (0, name)
    return (y * 10000 + m * 100 + d, name)


def find_agent_argv() -> list[str]:
    override = (settings.cursor_cli_bin or "").strip()
    if override:
        return [override]

    local = Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent"
    versions = local / "versions"
    if versions.is_dir():
        dirs = [
            p
            for p in versions.iterdir()
            if p.is_dir()
            and _VERSION_DIR_RE.match(p.name)
            and (p / "node.exe").is_file()
            and (p / "index.js").is_file()
        ]
        if dirs:
            latest = max(dirs, key=lambda p: _version_key(p.name))
            return [str(latest / "node.exe"), str(latest / "index.js")]

    cmd = local / "agent.cmd"
    if cmd.is_file():
        return [str(cmd)]

    for name in ("agent.cmd", "cursor-agent.cmd", "agent", "cursor-agent"):
        found = _which(name)
        if found:
            return [found]
    raise CursorCliError("Khong tim thay Cursor CLI (agent)")


def _which(name: str) -> str | None:
    from shutil import which

    found = which(name)
    if not found:
        return None
    path = Path(found)
    if path.suffix.lower() == ".ps1":
        sibling = path.with_suffix(".cmd")
        if sibling.is_file():
            return str(sibling)
        parent_cmd = path.parent / "agent.cmd"
        if parent_cmd.is_file():
            return str(parent_cmd)
    return found


def _run(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    key = (settings.cursor_api_key or "").strip()
    if key:
        env["CURSOR_API_KEY"] = key
    kwargs: dict = {
        "args": args,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "env": env,
        "cwd": str(workspace_dir()),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return subprocess.run(**kwargs)


def probe_cursor_cli() -> str:
    argv = find_agent_argv()
    proc = _run([*argv, "status", "--format", "json"], timeout=20)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise CursorCliError(err[-1] if err else f"status exit {proc.returncode}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise CursorCliError("status khong phai JSON") from exc
    if not data.get("isAuthenticated"):
        raise CursorCliError("Cursor CLI chua dang nhap (agent login)")
    return str(data.get("status") or "authenticated")


def _parse_print_json(stdout: str) -> tuple[str, str | None]:
    raw = (stdout or "").strip()
    if not raw:
        raise CursorCliError("Cursor CLI khong tra loi")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, None
    if not isinstance(data, dict):
        raise CursorCliError("Cursor CLI JSON la")
    if data.get("is_error"):
        raise CursorCliError(str(data.get("result") or "Cursor CLI is_error"))
    text = (data.get("result") or "").strip()
    if not text:
        raise CursorCliError("Cursor CLI result rong")
    sid = data.get("session_id")
    return text, str(sid) if sid else None


def ask_cursor_sync(prompt: str, *, resume_id: str | None = None) -> tuple[str, str | None]:
    text = (prompt or "").strip()
    if not text:
        raise CursorCliError("prompt trong")
    argv = find_agent_argv()
    args = [
        *argv,
        "-p",
        "--output-format",
        "json",
        "--mode",
        settings.cursor_cli_mode or "ask",
        "--model",
        settings.cursor_cli_model or "auto",
        "--trust",
        "--workspace",
        str(workspace_dir()),
    ]
    if resume_id:
        args.extend(["--resume", resume_id])
    args.append(text)
    timeout = float(settings.cursor_cli_timeout_s)
    try:
        proc = _run(args, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise CursorCliError(f"Cursor CLI timeout {timeout:.0f}s") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise CursorCliError(err[-1][:240] if err else f"exit {proc.returncode}")
    return _parse_print_json(proc.stdout)
