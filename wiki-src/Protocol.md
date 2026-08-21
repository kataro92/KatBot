# Protocol

Transport: WebSocket JSON (Xiaozhi-like) plus **raw PCM** binary frames (not Opus).

## Device socket

`ws://<pc-lan-ip>:8080/ws/device`

Handshake: server sends `hello` with `session_id` and `listen_ms`. Device replies
with firmware version, audio parameters, and its speaker capability. Server then
sends `config` with `listen_ms` and ESP playback `volume`.

### Device → server

| `type` | When |
| --- | --- |
| `hello` | After WS connect; includes `fw_version`, mic audio params, and `speaker` |
| `listen` | `state`: `start` or `stop` (button + timer on the ESP) |
| `telemetry` | DHT + `state` (`idle` / `listening` / `thinking` / `speaking`) + `listen_ms` |
| `abort` | Cancel |

Binary frames while `listening`: 16 kHz, 16-bit, mono PCM.

### Server → device

| `type` | When |
| --- | --- |
| `hello` | Session id, `listen_ms`, audio params (uplink 16 kHz PCM) |
| `config` | `{ "listen_ms": 5000, "volume": 80 }` |
| `listen` | `{ "state": "start" }` starts ESP capture from the monitor |
| `state` | e.g. `{ "value": "idle" }` |
| `tts` | `start`, `sentence_start` (caption), `stop` |

Binary frames while speaking: 16 kHz, 16-bit, mono PCM, ~1 KB chunks.

## Monitor socket

`ws://<pc>:8080/ws/monitor`

Browsers receive fan-out (`snapshot`, `telemetry`, `listen`, `log`, `chat`,
`state`, `tts_play`). PC-speaker playback uses `tts_play` with a WAV clip id.
Browsers never open a socket directly to the ESP.

## States

`offline` → `idle` → `listening` (timer on device) → `thinking` → `speaking` → `idle`
