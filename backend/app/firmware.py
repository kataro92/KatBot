"""Firmware management: list ports, compile, flash via arduino-cli."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import time
from pathlib import Path
from typing import AsyncIterator

from .config import ROOT_DIR, settings

log = logging.getLogger("meobot.firmware")

FQBN = "esp8266:esp8266:nodemcuv2"
SKETCH_DIR = ROOT_DIR / "firmware" / "KatBot"
BUILD_DIR = ROOT_DIR / "firmware" / "build"

_CLI = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arduino15", "arduino-cli.exe")

# Shared state
_status: dict = {"phase": "idle", "ok": None, "message": "", "ts": 0}
_flash_lock = asyncio.Lock()


def cli_path() -> str:
    override = getattr(settings, "arduino_cli_path", "")
    if override:
        return override
    if Path(_CLI).exists():
        return _CLI
    return "arduino-cli"


def _update_status(phase: str, message: str, ok: bool | None = None) -> None:
    _status.update({"phase": phase, "ok": ok, "message": message, "ts": int(time.time() * 1000)})


def get_status() -> dict:
    return dict(_status)


async def list_ports() -> list[dict]:
    """Return serial ports from arduino-cli board list as JSON."""
    try:
        proc = await asyncio.create_subprocess_exec(
            cli_path(), "board", "list", "--format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ARDUINO_DIRECTORIES_DATA": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arduino15")},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
    except FileNotFoundError:
        log.warning("arduino-cli not found at %s", cli_path())
        return []
    except asyncio.TimeoutError:
        log.warning("arduino-cli board list timed out")
        return []

    if proc.returncode != 0:
        log.warning("board list error: %s", stderr.decode(errors="replace"))
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    # arduino-cli >= 0.35 returns {"detected_ports": [...]}
    ports = data if isinstance(data, list) else data.get("detected_ports", [])
    result = []
    for p in ports:
        addr = p.get("port", {}).get("address") or p.get("address", "")
        proto = p.get("port", {}).get("protocol", "") or p.get("protocol", "")
        label = p.get("port", {}).get("label", "") or addr
        boards = p.get("matching_boards", [])
        board_name = boards[0].get("name", "") if boards else ""
        result.append({
            "port": addr,
            "protocol": proto,
            "label": label,
            "board": board_name,
        })
    return [r for r in result if r["port"]]


async def _stream_subprocess(
    args: list[str],
    env: dict | None = None,
) -> AsyncIterator[str]:
    """Yield output lines from a subprocess, then a sentinel {"exit_code": N}."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env or os.environ.copy(),
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        yield line.decode(errors="replace").rstrip("\n\r")
    await proc.wait()
    yield json.dumps({"exit_code": proc.returncode})


async def run_compile() -> AsyncIterator[str]:
    """Compile firmware and yield log lines (SSE-ready strings)."""
    if _flash_lock.locked():
        yield "data: Đang có tác vụ khác đang chạy, vui lòng đợi.\n\n"
        return

    async with _flash_lock:
        _update_status("compiling", "Đang biên dịch…")
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
        args = [
            cli_path(),
            "compile",
            "--fqbn", FQBN,
            "--warnings", "default",
            "--build-path", str(BUILD_DIR),
            str(SKETCH_DIR),
        ]
        env = {
            **os.environ,
            "ARDUINO_DIRECTORIES_DATA": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arduino15"),
            "ARDUINO_DIRECTORIES_USER": os.path.join(os.environ.get("USERPROFILE", ""), "Documents", "Arduino"),
        }
        log.info("compile: %s", shlex.join(args))
        yield "data: Bắt đầu biên dịch firmware…\n\n"
        exit_code = 0
        async for line in _stream_subprocess(args, env):
            try:
                obj = json.loads(line)
                exit_code = obj.get("exit_code", 0)
                if exit_code == 0:
                    _update_status("idle", "Biên dịch thành công.", ok=True)
                    yield "data: ✓ Biên dịch thành công.\n\n"
                else:
                    _update_status("error", f"Lỗi biên dịch (exit {exit_code}).", ok=False)
                    yield f"data: ✗ Biên dịch lỗi (exit code {exit_code}).\n\n"
                yield "data: [DONE]\n\n"
            except json.JSONDecodeError:
                # Filter noisy progress lines but keep errors
                clean = line.strip()
                if clean:
                    yield f"data: {clean}\n\n"


async def run_flash(port: str) -> AsyncIterator[str]:
    """Flash compiled firmware to `port` and yield log lines."""
    elf = BUILD_DIR / "KatBot.ino.elf"
    if not elf.exists():
        yield "data: Chưa có bản compile. Hãy biên dịch trước.\n\n"
        yield "data: [DONE]\n\n"
        return

    if _flash_lock.locked():
        yield "data: Đang có tác vụ khác đang chạy, vui lòng đợi.\n\n"
        return

    async with _flash_lock:
        _update_status("flashing", f"Đang nạp lên {port}…")
        args = [
            cli_path(),
            "upload",
            "--fqbn", FQBN,
            "--port", port,
            "--input-dir", str(BUILD_DIR),
            str(SKETCH_DIR),
        ]
        env = {
            **os.environ,
            "ARDUINO_DIRECTORIES_DATA": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arduino15"),
            "ARDUINO_DIRECTORIES_USER": os.path.join(os.environ.get("USERPROFILE", ""), "Documents", "Arduino"),
        }
        log.info("flash to %s: %s", port, shlex.join(args))
        yield f"data: Bắt đầu nạp firmware lên {port}…\n\n"
        async for line in _stream_subprocess(args, env):
            try:
                obj = json.loads(line)
                exit_code = obj.get("exit_code", 0)
                if exit_code == 0:
                    _update_status("idle", f"Nạp thành công lên {port}.", ok=True)
                    yield f"data: ✓ Nạp thành công lên {port}.\n\n"
                else:
                    _update_status("error", f"Lỗi nạp (exit {exit_code}).", ok=False)
                    yield f"data: ✗ Nạp lỗi (exit code {exit_code}).\n\n"
                yield "data: [DONE]\n\n"
            except json.JSONDecodeError:
                clean = line.strip()
                if clean:
                    yield f"data: {clean}\n\n"
