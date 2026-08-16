# Backend

Python FastAPI on the PC. One warm [Ollama](https://ollama.com/) chat session. The web UI is served from the same process.

## Start

From the repo root, run `start.bat`. It will:

1. Create `backend/.venv` if missing
2. Activate the venv
3. Install packages from `backend/requirements.txt`
4. Copy `.env.example` → `.env` if `.env` is missing
5. Listen on `0.0.0.0:8080`

Open http://127.0.0.1:8080 — text chat tests Ollama before you flash the ESP.

Ollama must already be running.

## Environment (repo-root `.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API |
| `OLLAMA_MODEL` | `llama3.2` | Any local model you pulled |
| `OLLAMA_KEEP_ALIVE` | `-1` | Keep the model in RAM |
| `OLLAMA_NUM_PREDICT` | `80` | Short replies |

`STT_*` and `TTS_*` are for later stages. Do not commit `.env`.

## Endpoints

| Path | Role |
| --- | --- |
| `/` | Monitor page |
| `/api/health` | Ollama + device status |
| `/api/chat` | Text test against the same session |
| `/ws/device` | ESP-12F |
| `/ws/monitor` | Browsers (fan-out only) |

System prompt (Vietnamese): short cute answers, no emoji, no extra explanation.
