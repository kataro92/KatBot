"""HTTP + WebSocket checks for the Mèo Bot API. Run: python test_api.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import httpx

from app.main import app
from app.version import web_asset_version

FAIL = 0


def ok(name: str, cond: bool, detail: str = "") -> None:
    global FAIL
    if cond:
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        extra = f" — {detail}" if detail else ""
        print(f"  FAIL  {name}{extra}")


def recv_json_until(ws, predicate, attempts: int = 12):
    last = None
    for _ in range(attempts):
        try:
            last = json.loads(ws.receive_text())
        except Exception:
            break
        if predicate(last):
            return last
    return last


def main() -> int:
    global FAIL
    print("Meo Bot API tests")
    expected_ver = web_asset_version()

    with TestClient(app) as client:
        client.timeout = httpx.Timeout(180.0)
        r = client.get("/")
        ok("GET /", r.status_code == 200 and "Mèo Bot" in r.text)
        ok("GET / Cache-Control", "no-store" in r.headers.get("cache-control", "").lower())

        r = client.get("/static/app.js")
        ok("GET /static/app.js", r.status_code == 200 and "checkFrontendVersion" in r.text)
        ok(
            "GET /static/app.js Cache-Control",
            "no-store" in r.headers.get("cache-control", "").lower(),
        )

        r = client.get("/static/styles.css")
        ok("GET /static/styles.css", r.status_code == 200 and ".pill" in r.text)

        r = client.get("/api/version")
        body = r.json()
        ok("GET /api/version", r.status_code == 200 and body.get("version") == expected_ver)

        r = client.get("/api/health")
        h = r.json()
        ok(
            "GET /api/health",
            r.status_code == 200
            and h.get("ok") is True
            and "state" in h
            and "model" in h
            and "ollama_ready" in h
            and h.get("version") == expected_ver,
            detail=str(h),
        )

        r = client.post("/api/chat", json={})
        ok("POST /api/chat empty", r.status_code == 422)

        r = client.post("/api/chat", json={"text": ""})
        ok("POST /api/chat blank", r.status_code == 422)

        print("  ... POST /api/chat (Ollama + TTS, may take a while)")
        r = client.post("/api/chat", json={"text": "Xin chào, trả lời đúng một từ: meo"})
        chat = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok(
            "POST /api/chat",
            r.status_code == 200 and "reply" in chat and chat.get("error") == "",
            detail=str(chat),
        )

        with client.websocket_connect("/ws/device") as ws:
            hello = json.loads(ws.receive_text())
            ok(
                "WS /ws/device hello",
                hello.get("type") == "hello" and hello.get("audio_params", {}).get("format") == "pcm",
            )
            ws.send_text(json.dumps({"type": "hello", "fw": "test"}))
            ws.send_text(
                json.dumps({"type": "telemetry", "temp": 26.5, "humidity": 55.0, "state": "idle"})
            )
            ws.send_text(json.dumps({"type": "listen", "state": "start"}))
            ws.send_bytes(b"\x00\x00" * 200)
            ws.send_text(json.dumps({"type": "listen", "state": "stop"}))
            idle = recv_json_until(
                ws,
                lambda m: m.get("type") == "state" and m.get("value") == "idle",
            )
            ok(
                "WS /ws/device listen short idle",
                idle is not None and idle.get("type") == "state",
                detail=str(idle),
            )

        r = client.get("/api/health")
        ok(
            "GET /api/health after device disconnect",
            r.status_code == 200 and r.json().get("ok") is True and r.json().get("device_online") is False,
        )

        with client.websocket_connect("/ws/monitor") as mon:
            snap = json.loads(mon.receive_text())
            ok("WS /ws/monitor snapshot", snap.get("type") == "snapshot")
            with client.websocket_connect("/ws/device") as dev:
                hello = json.loads(dev.receive_text())
                ok("WS /ws/device hello (2)", hello.get("type") == "hello")
                connected = recv_json_until(
                    mon,
                    lambda m: m.get("type") == "snapshot" and m.get("device_online") is True,
                )
                ok(
                    "WS /ws/monitor device snapshot",
                    connected is not None and connected.get("type") == "snapshot",
                    detail=str(connected),
                )
                dev.send_text(
                    json.dumps({"type": "telemetry", "temp": 27.0, "humidity": 50.0, "state": "idle"})
                )
                tel = recv_json_until(mon, lambda m: m.get("type") == "telemetry")
                ok(
                    "WS /ws/monitor telemetry",
                    tel is not None and tel.get("type") == "telemetry" and tel.get("temp") == 27.0,
                    detail=str(tel),
                )

        r = client.get("/no-such-page")
        ok("GET unknown 404", r.status_code == 404)

    print()
    if FAIL:
        print(f"{FAIL} test(s) failed")
        return 1
    print("All API tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
