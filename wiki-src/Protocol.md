# Protocol

Transport: WebSocket JSON (Xiaozhi-like). Audio will be raw PCM later, not Opus.

## Device socket

`ws://<pc-lan-ip>:8080/ws/device`

Handshake: server sends `hello` with `session_id`. Device sends `hello` on connect.

### Device → server

| `type` | When |
| --- | --- |
| `hello` | After WS connect |
| `listen` | `state`: `start` or `stop` (button + 5 s timer on the ESP) |
| `telemetry` | DHT + `state` (`idle` / `listening` / …) |
| `abort` | Cancel |

Binary frames: reserved for PCM uplink.

### Server → device

| `type` | When |
| --- | --- |
| `hello` | Session id + audio params |
| `state` | e.g. `{ "value": "idle" }` |
| `stt` / `tts` | Later (pipeline) |

## Monitor socket

`ws://<pc>:8080/ws/monitor`

Browsers only receive fan-out (`snapshot`, `telemetry`, `listen`, `log`, `chat`). They never open a socket to the ESP.

## States

`offline` → `idle` → `listening` (5 s) → `thinking` → `speaking` → `idle`
