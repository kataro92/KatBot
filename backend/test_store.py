"""SQLite history store unit tests."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.store import Store, window_bounds


def _check(cond: bool, name: str) -> int:
    if cond:
        print("PASS", name)
        return 0
    print("FAIL", name)
    return 1


def main() -> int:
    fail = 0
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "t.sqlite"
        store = Store(path)
        store.open()
        base = 1_700_000_000_000
        for i in range(10):
            store.insert_telemetry(base + i * 1000, 20 + i, 40 + i, "idle", True, "abc")
        store.insert_chat(base + 5, "user", "xin chào", "clip1")
        store.insert_chat(base + 6, "assistant", "meo", None)
        store.insert_log(base + 7, "info", "hello")
        store.insert_log(base + 8, "debug", "skip me")

        pts = store.telemetry(base, base + 20_000)
        fail += _check(len(pts) == 10, "telemetry points")
        fail += _check(pts[0]["temp"] == 20, "first temp")
        fail += _check(pts[-1]["humidity"] == 49, "last humidity")

        wide = store.telemetry(base, base + 60_000)
        fail += _check(len(wide) >= 1, "bucketed telemetry")

        chats = store.chat(limit=10)
        fail += _check(len(chats) == 2, "chat count")
        fail += _check(chats[0]["text"] == "xin chào" and chats[0]["audio_id"] == "clip1", "chat order")
        fail += _check(chats[1]["role"] == "assistant", "assistant row")

        logs = store.logs(limit=10)
        fail += _check(len(logs) == 2, "log count includes debug when inserted directly")

        start, end = window_bounds("1h", None, None)
        fail += _check(end - start == 3_600_000, "window 1h")
        try:
            window_bounds(None, 10, 5)
            fail += _check(False, "invalid range")
        except ValueError:
            fail += _check(True, "invalid range")
        store.close()
    return fail


if __name__ == "__main__":
    n = main()
    if n:
        print(f"{n} failed")
        raise SystemExit(1)
    print("All store tests passed")
    raise SystemExit(0)
