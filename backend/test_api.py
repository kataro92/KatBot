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

from app.clips import pcm16_to_wav, put_pcm
from app.config import settings
from app.main import app
from app.version import web_asset_version

settings.cursor_cli_enabled = False
_db = ROOT / "data" / "test-katbot.sqlite"
_db.parent.mkdir(parents=True, exist_ok=True)
for leftover in _db.parent.glob("test-katbot.sqlite*"):
    leftover.unlink(missing_ok=True)
settings.db_path = str(_db)

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
        ok(
            "GET /",
            r.status_code == 200
            and "Mèo Bot" in r.text
            and "chartRanges" in r.text
            and "micSource" in r.text
            and "talkBtn" in r.text
            and "audio-panel" in r.text
            and "fwVersion" in r.text,
        )
        ok("GET / Cache-Control", "no-store" in r.headers.get("cache-control", "").lower())

        r = client.get("/static/app.js")
        ok("GET /static/app.js", r.status_code == 200 and "loadHistory" in r.text)
        ok(
            "GET /static/app.js Cache-Control",
            "no-store" in r.headers.get("cache-control", "").lower(),
        )

        r = client.get("/static/styles.css")
        ok("GET /static/styles.css", r.status_code == 200 and ".play-clip" in r.text)

        r = client.get("/api/clips/missing")
        ok("GET /api/clips missing", r.status_code == 404)

        cid = put_pcm(b"\x00\x00" * 400, 8000)
        r = client.get(f"/api/clips/{cid}")
        ok(
            "GET /api/clips wav",
            r.status_code == 200
            and r.headers.get("content-type", "").startswith("audio/wav")
            and r.content[:4] == b"RIFF"
            and r.content[8:12] == b"WAVE"
            and len(r.content) > 44,
        )
        ok("wav payload matches", r.content == pcm16_to_wav(b"\x00\x00" * 400, 8000))

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
            and "cursor_cli_ready" in h
            and "temp" in h
            and "web_search" in h
            and "listen_ms" in h
            and "mic_source" in h
            and "speaker" in h
            and "fw_version" in h
            and "stt_engine" in h
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

        r = client.get("/api/history/telemetry?window=15m")
        tel = r.json() if r.status_code == 200 else {}
        ok(
            "GET /api/history/telemetry",
            r.status_code == 200
            and "points" in tel
            and "from_ms" in tel
            and tel["to_ms"] > tel["from_ms"],
            detail=str(tel)[:200],
        )

        r = client.get("/api/history/telemetry?from_ms=100&to_ms=50")
        ok("GET /api/history/telemetry bad range", r.status_code == 400)

        r = client.get("/api/history/chat")
        chats = r.json() if r.status_code == 200 else {}
        ok(
            "GET /api/history/chat",
            r.status_code == 200 and isinstance(chats.get("items"), list) and len(chats["items"]) >= 2,
            detail=str(chats)[:240],
        )

        r = client.get("/api/history/logs")
        logs = r.json() if r.status_code == 200 else {}
        ok(
            "GET /api/history/logs",
            r.status_code == 200 and isinstance(logs.get("items"), list) and len(logs["items"]) >= 1,
            detail=str(logs)[:240],
        )

        r = client.post("/api/audio-route", json={"mic": "pc", "speaker": "pc"})
        route = r.json() if r.status_code == 200 else {}
        ok(
            "POST /api/audio-route pc",
            r.status_code == 200 and route.get("mic_source") == "pc" and route.get("speaker") == "pc",
            detail=str(route),
        )
        r = client.post("/api/listen?hz=16000", content=b"\x00\x00" * 200)
        listen = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok(
            "POST /api/listen short",
            r.status_code == 200 and listen.get("ok") == "1",
            detail=str(listen)[:200],
        )
        r = client.post(
            "/api/audio-route",
            json={"mic": "esp", "speaker": "esp", "esp_volume": 65},
        )
        ok(
            "POST /api/audio-route esp volume",
            r.status_code == 200
            and r.json().get("mic_source") == "esp"
            and r.json().get("esp_volume") == 65,
        )
        r = client.post("/api/audio-route", json={"esp_volume": 101})
        ok("POST /api/audio-route bad volume", r.status_code == 422)

        r = client.post("/api/listen?hz=16000", content=b"\x00\x00" * 200)
        ok("POST /api/listen mic not pc", r.status_code == 400)

        r = client.post("/api/listen/start")
        ok(
            "POST /api/listen/start esp offline",
            r.status_code == 400,
            detail=str(r.json())[:160],
        )

        r = client.get("/api/firmware/releases")
        rel = r.json() if r.status_code == 200 else {}
        ok(
            "GET /api/firmware/releases",
            r.status_code == 200
            and isinstance(rel.get("releases"), list)
            and "source" in rel
            and isinstance(rel.get("profiles"), list)
            and any(p.get("id") == "mic" for p in rel.get("profiles") or []),
            detail=str(rel)[:280],
        )
        r = client.post("/api/firmware/flash", json={"port": "COM9", "version": "not-a-ver"})
        ok("POST /api/firmware/flash bad version", r.status_code == 400)
        r = client.post("/api/firmware/flash", json={"port": "COM9", "version": "9.9.9"})
        body = ""
        if r.status_code == 200:
            body = r.text
        ok(
            "POST /api/firmware/flash missing release",
            r.status_code == 200 and "9.9.9" in body,
            detail=body[:200],
        )

        with client.websocket_connect("/ws/device") as ws:
            hello = json.loads(ws.receive_text())
            ok(
                "WS /ws/device hello",
                hello.get("type") == "hello"
                and hello.get("audio_params", {}).get("format") == "pcm"
                and isinstance(hello.get("listen_ms"), int)
                and hello["listen_ms"] >= 1000,
            )
            ws.send_text(
                json.dumps(
                    {
                        "type": "hello",
                        "fw_version": "0.0.1",
                        "audio_params": {"sample_rate": 16000},
                    }
                )
            )
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
                client.post("/api/audio-route", json={"mic": "pc", "speaker": "esp"})
                r = client.post("/api/listen/start")
                start_pc = r.json() if r.status_code == 200 else {}
                ok(
                    "POST /api/listen/start pc",
                    r.status_code == 200 and start_pc.get("source") == "pc",
                    detail=str(start_pc),
                )
                client.post("/api/audio-route", json={"mic": "esp", "speaker": "esp"})
                r = client.post("/api/listen/start")
                ok(
                    "POST /api/listen/start esp online",
                    r.status_code == 200 and (r.json() or {}).get("source") == "esp",
                    detail=str(r.json())[:160],
                )
                client.post("/api/audio-route", json={"mic": "pc", "speaker": "esp"})
                dev.send_text(json.dumps({"type": "listen", "state": "start"}))
                pc_listen = recv_json_until(
                    mon,
                    lambda m: m.get("type") == "listen"
                    and m.get("state") == "start"
                    and m.get("source") == "pc",
                    attempts=20,
                )
                ok(
                    "WS ESP button triggers PC listen",
                    pc_listen is not None and pc_listen.get("source") == "pc",
                    detail=str(pc_listen),
                )
                dev.send_text(json.dumps({"type": "listen", "state": "stop"}))
                client.post("/api/audio-route", json={"mic": "esp", "speaker": "esp"})

        r = client.get("/api/history/telemetry?window=1h")
        pts = (r.json() or {}).get("points") or []
        ok(
            "GET history telemetry after DHT",
            r.status_code == 200
            and any(p.get("temp") is not None and abs(p["temp"] - 27.0) < 1.5 for p in pts),
            detail=str(pts[-3:]),
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
