# Protocol

Transport: WebSocket JSON (Xiaozhi-like) plus **raw PCM** binary frames (not Opus).

## Device socket

`ws://<pc-lan-ip>:8080/ws/device`

Handshake: server sends `hello` with `session_id` and `listen_ms`. Device sends `hello` on connect. Server then sends `config` with `listen_ms` so the chip matches the backend window.

### Device → server

| `type` | When |
| --- | --- |
| `hello` | After WS connect |
| `listen` | `state`: `start` or `stop` (button + timer on the ESP) |
| `telemetry` | DHT + `state` (`idle` / `listening` / `thinking` / `speaking`) + `listen_ms` |
| `abort` | Cancel |

Binary frames while `listening`: 16 kHz, 16-bit, mono PCM.

### Server → device

| `type` | When |
| --- | --- |
| `hello` | Session id, `listen_ms`, audio params (uplink 16 kHz PCM) |
| `config` | `{ "listen_ms": 5000 }` |
| `state` | e.g. `{ "value": "idle" }` |
| `tts` | `start`, `sentence_start` (caption), `stop` |

Binary frames while speaking: 16 kHz, 16-bit, mono PCM, ~1 KB chunks.

## Monitor socket

`ws://<pc>:8080/ws/monitor`

Browsers only receive fan-out (`snapshot`, `telemetry`, `listen`, `log`, `chat`, `state`). They never open a socket to the ESP.

## States

`offline` → `idle` → `listening` (timer on device) → `thinking` → `speaking` → `idle`
