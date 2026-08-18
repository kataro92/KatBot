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

`ELEVENLABS_API_KEY` is required only for `STT_ENGINE=elevenlabs`. Do not commit `.env`.

## Voice turn

`listen stop` (or `/api/chat`) runs one lock-protected turn:

1. **STT** (mic path only) — 8 kHz PCM → text
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
| `/ws/device` | ESP-12F (JSON + PCM) |
| `/ws/monitor` | Browsers (fan-out only) |

## Monitor

The dashboard shows ESP online/offline, a 3-minute DHT chart, the listen countdown, chat, and the event log. It never opens a socket to the chip.

## Tests

From `backend/` with the project venv:

```
.venv\Scripts\python.exe test_api.py
.venv\Scripts\python.exe test_context.py
.venv\Scripts\python.exe test_web_search.py
.venv\Scripts\python.exe test_tools.py
```
