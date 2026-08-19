# Backend

Python FastAPI on the PC. One shared chat session for the device and the monitor. The web UI is served from the same process.

## Start

From the repo root, run `start.bat`. It will:

1. Create `backend/.venv` if missing
2. Activate the venv
3. Install packages from `backend/requirements.txt`
4. Copy `.env.example` → `.env` if `.env` is missing
5. Listen on `0.0.0.0:8080`

Open http://127.0.0.1:8080 — typed chat uses the same turn as the mic (tools + LLM + TTS on the ESP when it is online).

Ollama should already be running. Cursor CLI is optional; if it is missing, chat falls back to Ollama.

## Environment (repo-root `.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address |
| `LISTEN_MS` | `5000` | Listen window pushed to the ESP |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API |
| `OLLAMA_MODEL` | `llama3.2` | Fallback chat / compose model |
| `OLLAMA_KEEP_ALIVE` | `-1` | Keep the model in RAM |
| `OLLAMA_NUM_PREDICT` | `80` | Short replies |
| `OLLAMA_NUM_PREDICT_TOOLS` | `240` | Longer replies after search |
| `CURSOR_CLI_ENABLED` | `true` | Try Cursor CLI (ask mode, model Auto) first |
| `CURSOR_CLI_TIMEOUT_S` | `60` | CLI timeout |
| `STT_ENGINE` | `phowhisper` | `phowhisper`, `faster-whisper`, or `elevenlabs` |
| `PHOWHISPER_MODEL` | `vinai/PhoWhisper-small` | CT2 PhoWhisper size |
| `WHISPER_MODEL` | `small` | Size when `STT_ENGINE=faster-whisper` |
| `STT_LANGUAGE` | `vi` | ASR language |
| `STT_DEVICE` | `auto` | `cpu` / `cuda`; auto uses CUDA only if VRAM ≥ 4 GB |
| `TTS_ENGINE` | `gtts` | Vietnamese TTS |
| `WEB_SEARCH_ENABLED` | `true` | Tools + web lookup |
| `WEATHER_CITY` | `Ha Noi` | Default outdoor city |
| `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` | (empty) | Optional Custom Search; otherwise Startpage/Brave/DDG |
| `DB_PATH` | `backend/data/katbot.sqlite` | SQLite history (telemetry, chat, logs) |

`ELEVENLABS_API_KEY` is required only for `STT_ENGINE=elevenlabs`. Do not commit `.env`.

## Voice turn

`listen stop` (or `/api/chat`) runs one lock-protected turn:

1. **STT** (mic path only) — 16 kHz PCM → text
2. **Tools** — music, time, indoor DHT11, outdoor weather (Open-Meteo), USD/VND, then Wikipedia / news / web
3. **LLM** — Cursor CLI if enabled, else Ollama. Search hits are composed into a short spoken answer (no URLs, no emoji)
4. **TTS** — gTTS → 16 kHz PCM chunks over the device WebSocket

Indoor “how warm is it here” uses the DHT11 reading injected into the system prompt. Outdoor “Hà Nội hôm nay” uses Open-Meteo, not the sensor.

## Endpoints

| Path | Role |
| --- | --- |
| `/` | Monitor page |
| `/api/health` | Ollama, Cursor CLI, STT, device, DHT, listen window |
| `/api/chat` | Same pipeline as a spoken turn |
| `/api/version` | Web asset fingerprint (cache bust) |
| `/api/history/telemetry` | DHT chart points (`window=` or `from_ms`/`to_ms`) |
| `/api/history/chat` | Persisted chat |
| `/api/history/logs` | Persisted event log |
| `/api/clips/{id}` | WAV playback of a spoken user clip |
| `/api/firmware/ports` | List COM ports from `arduino-cli` |
| `/api/firmware/status` | Current compile / flash state |
| `/api/firmware/compile` | Stream compile log (SSE) |
| `/api/firmware/flash` | Stream upload log (SSE) |
| `/ws/device` | ESP-12F (JSON + PCM) |
| `/ws/monitor` | Browsers (fan-out only) |

## Monitor

Pastel glass dashboard (`web/`): frost cards, blush/mint/lavender wash, **Be Vietnam Pro** headings and **Inter** body (both have a Vietnamese subset). It shows ESP online/offline, a DHT chart (1 phút / 15 phút / 1–12 tiếng / 1 ngày / tùy chọn; temperature solid, humidity dashed), the listen countdown, chat bubbles, and the event log. Spoken user lines get a play button (`/api/clips`). Chat, logs, and telemetry are stored in SQLite (`DB_PATH`) and reloaded after refresh. The browser never opens a socket to the chip.

There is also a **Firmware** card in the monitor: detect COM ports, compile with `arduino-cli`, and upload from the browser through the local FastAPI backend. Compile / flash logs stream back as SSE.

## Tests

From `backend/` with the project venv:

```
.venv\Scripts\python.exe test_api.py
.venv\Scripts\python.exe test_store.py
.venv\Scripts\python.exe test_context.py
.venv\Scripts\python.exe test_web_search.py
.venv\Scripts\python.exe test_tools.py
```
