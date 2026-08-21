# KatBot (Mèo Bot)

Local voice chatbot on an **ESP-12F / NodeMCU**. The chip is a thin client; speech, LLM, tools, and the web monitor run on your PC so the microcontroller stays light.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Wiki](https://img.shields.io/badge/docs-wiki-blue)](https://github.com/kataro92/KatBot/wiki)

![Kiến trúc KatBot](docs/architecture.png)

Inspired by [Xiaozhi](https://github.com/78/xiaozhi-esp32) (WebSocket session, listen/speak states), but fully local via [Ollama](https://ollama.com/) (with optional [Cursor CLI](https://cursor.com/) for chat). ESP-12F is an ESP8266 — this repo does **not** port Xiaozhi firmware (no ESP-SR wake word, no Opus, no AEC).

The browser talks only to the PC. It never loads the ESP.

**Docs:** [Wiki](https://github.com/kataro92/KatBot/wiki) · [Hardware & wiring](https://github.com/kataro92/KatBot/wiki/Hardware) · [Backend](https://github.com/kataro92/KatBot/wiki/Backend) · [Firmware](https://github.com/kataro92/KatBot/wiki/Firmware) · [Protocol](https://github.com/kataro92/KatBot/wiki/Protocol)

## Status

| Stage | What | State |
| --- | --- | --- |
| 0–1 | Backend, warm LLM session, web monitor, Wi-Fi, OLED, DHT11, listen button | Done |
| 2 | TTS playback over I2S (MAX98357, 16 kHz PCM) | Done |
| 3 | Mic capture (INMP441 I2S → 16 kHz PCM → STT) | Done |
| 4 | Full talk loop: listen → STT → tools/LLM → TTS | Done |
| 5 | Chibi OLED UI, boot SFX, reconnect, tools (weather / FX / search / music) | Done |

## Features (current)

- Press the button once → firmware opens a **5 second** listen window (not hold-to-talk; `LISTEN_MS` in `.env` and `config.h`)
- Mic streams 16 kHz PCM to the PC from an **INMP441** I2S MEMS mic; STT default is **PhoWhisper** (faster-whisper and ElevenLabs Scribe are optional)
- Chat: **Cursor CLI** (model Auto) first, **Ollama** fallback (`llama3.2` by default)
- Tools when the utterance needs them: indoor DHT11, outdoor weather, USD/VND, Wikipedia/news/web, and music searched in priority order **YouTube → Zing MP3 → SoundCloud → other**
- Select ESP or PC microphone/speaker from the monitor; ESP speaker volume is adjustable from 0–100%
- Two firmware profiles share one sketch: **mic+loa `v0.2.x`** and **mic-only `v0.1.x`**
- OLED chibi cat UI shows firmware version, status (`idle` / `nghe` / `nghi` / `noi`), temperature, and humidity
- Replies are **tiếng Việt có dấu** (Cursor CLI and Ollama prompts require diacritics)
- Web monitor (pastel glass UI, [Be Vietnam Pro](https://fonts.google.com/specimen/Be+Vietnam+Pro) + [Inter](https://fonts.google.com/specimen/Inter)): ESP status, DHT chart with ranges (1 phút → 1 ngày, or custom), listen bar, chat bubbles, event log. Spoken user lines have a play button. Typed chat uses the same pipeline and speaks on the ESP when it is online
- SQLite history (`backend/data/katbot.sqlite`) keeps telemetry, chat, and logs across refresh

Device states: `idle` → `listening` (timer on the chip) → `thinking` → `speaking` → `idle`. Extra presses while busy are ignored (no barge-in).

## Hardware

| Part | Role |
| --- | --- |
| ESP-12F on NodeMCU v1.0 | Wi-Fi MCU |
| SSD1306 0.96" I2C (e.g. JMD0.96D-1) | Display |
| INMP441 | I2S MEMS mic |
| MAX98357 + 3 W speaker | I2S amp |
| DHT11 | Temperature / humidity |
| Momentary button | Listen trigger, active LOW |

No Arduino Uno coprocessor.

### Wiring

![Sơ đồ cắm dây KatBot](docs/wiring.png)

### Pin map (NodeMCU labels)

Mic và loa dùng **hai bus I2S tách** trên ESP8266: mic = `I2SI_*`, loa = `I2SO_*` (không dùng chung SCK/WS).

#### SSD1306 0.96" I2C (`0x3C`)

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| GND | GND | — | Common ground |
| VCC | 3V3 | — | 3.3 V |
| SCL | D1 | 5 | I2C clock |
| SDA | D2 | 4 | I2C data |

JMD0.96D-1 pin order is commonly **GND–VCC–SCL–SDA**. Follow silkscreen if VCC/GND are swapped.

#### INMP441 (I2S mic) — cả full và chỉ-mic

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| VDD | 3V3 | — | 3.3 V |
| GND | GND | — | Common ground |
| L/R | GND | — | Left channel |
| SD | **D6** | 12 | `I2SI_DATA` |
| SCK | **D7** | 13 | `I2SI_BCK` |
| WS | **D5** | 14 | `I2SI_WS` |

#### MAX98357 + speaker — chỉ bản mic+loa (`v0.2.x`)

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| VIN | Vin | — | 5 V USB / battery boost (3 W) |
| GND | GND | — | Common ground |
| DIN | **RX** | 3 | `I2SO_DATA`; no `Serial` debug |
| BCLK | **D8** | 15 | `I2SO_BCK` (không dùng chung mic) |
| LRC | **D4** | 2 | `I2SO_WS` |
| GAIN | — | — | Leave floating (default gain) |
| SD | 3V3 | — | Keep amplifier enabled |
| Speaker + / − | MAX98357 + / − | — | Never wire the speaker to the ESP |

Bản **chỉ mic**: không cắm amp/loa.

#### DHT11

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| VCC | 3V3 | — | 3.3 V |
| DATA | **D0** | 16 | Add a **4.7–10 kΩ pull-up resistor** from DATA to 3V3 |
| GND | GND | — | Common ground |

GPIO16 has no internal pull-up; the resistor is required even though firmware
uses a dedicated DHT11 reader for this pin. A 3-pin DHT11 module may already
include it—check the module PCB.

#### Listen button

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| A | **D3** | 0 | `INPUT_PULLUP`, active LOW (không giữ lúc boot) |
| B | GND | — | Press connects D3 to GND |

Firmware switches I2S between RX (listen) and TX (speak). No full-duplex / barge-in.

Battery: feed **regulated 5 V into `Vin`**, not 3.7 V into `3V3`. See [Wiki → Hardware](https://github.com/kataro92/KatBot/wiki/Hardware).

## Repository layout

```
KatBot/
  start.bat         Start backend (venv + deps + server)
  compile.bat       Compile firmware with arduino-cli
  backend/          FastAPI (device WS, monitor WS, STT, LLM, TTS, tools, SQLite)
  firmware/KatBot/  Arduino sketch for NodeMCU
  firmware/tools/   OLED sprite generator (`ref_cat.png` → `cat_bitmaps.h`)
  web/              Monitor UI (pastel glass, served by the backend)
  design-system/    UI tokens for the monitor (glass + Vietnamese fonts)
  docs/             Architecture and wiring diagrams
  wiki-src/         GitHub Wiki source
  .env.example      Backend settings (no secrets)
  LICENSE           MIT
```

## Requirements

**PC:** Python 3.12+, [Ollama](https://ollama.com/) with a local model (default `llama3.2`), same LAN as the NodeMCU. Optional: Cursor CLI on PATH (used first for chat when `CURSOR_CLI_ENABLED=true`).

**Firmware:** Arduino IDE or arduino-cli, ESP8266 core, board **NodeMCU 1.0 (ESP-12E)** (`esp8266:esp8266:nodemcuv2`). Libraries: see [`firmware/libraries.txt`](firmware/libraries.txt) (Adafruit SSD1306, Adafruit GFX, ArduinoJson, WebSockets). DHT11 on GPIO16 uses the sketch's dedicated reader, not the Adafruit DHT library. WebSockets should use a 2 KB `MAX_DATA_SIZE`.

## Quick start

### 1. Backend

Double-click [`start.bat`](start.bat) in the repo root. It creates `backend/.venv` if needed, installs missing packages, copies `.env` from `.env.example` when absent, then starts the server.

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) (or `http://<pc-lan-ip>:8080`). The monitor is served by the backend; the browser never talks directly to the ESP. Its audio controls select ESP/PC input and output and adjust ESP volume. The **Firmware** card compiles either profile, archives versioned binaries, and flashes a selected release. Chart, chat, and logs reload from SQLite.

Ollama must already be running. On startup the backend preloads the model (`keep_alive=-1`) and warms STT.

Useful env vars (repo-root `.env`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address (`0.0.0.0` so the ESP can connect) |
| `LISTEN_MS` | `5000` | Listen window; sent to the ESP on connect |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API |
| `OLLAMA_MODEL` | `llama3.2` | Fallback chat model |
| `OLLAMA_KEEP_ALIVE` | `-1` | Keep the model loaded |
| `OLLAMA_NUM_PREDICT` | `80` | Short replies |
| `CURSOR_CLI_ENABLED` | `true` | Prefer local Cursor CLI, then Ollama |
| `STT_ENGINE` | `phowhisper` | `phowhisper` \| `faster-whisper` \| `elevenlabs` |
| `TTS_ENGINE` | `gtts` | Vietnamese speech via gTTS |
| `WEB_SEARCH_ENABLED` | `true` | Weather / FX / Wikipedia / news / web |
| `WEATHER_CITY` | `Ha Noi` | Default city when none is named |
| `DB_PATH` | `backend/data/katbot.sqlite` | SQLite history (telemetry, chat, logs) |

Do not commit `.env` or API keys. More: [Wiki → Backend](https://github.com/kataro92/KatBot/wiki/Backend).

### 2. Firmware

1. Copy [`firmware/KatBot/secrets.h.example`](firmware/KatBot/secrets.h.example) to `firmware/KatBot/secrets.h`.
2. Set `WIFI_SSID`, `WIFI_PASS`, and `WS_HOST` to this PC’s LAN IPv4. `secrets.h` is gitignored.
3. Select **NodeMCU 1.0 (ESP-12E)**, the correct COM port, **CPU 160 MHz**, 115200 baud.
4. In the monitor, select **mic+loa** or **chỉ mic**, compile, then flash the archived release. [`compile.bat`](compile.bat) builds the default full profile.
5. OLED: Wi-Fi, a short boot jingle, then idle with the cat sprite when the WebSocket is up. The dashboard should show **ESP online**.

Press the listen button once (do not hold). OLED shows `nghe` and a countdown; after 5 s it shows `nghi`, then speaks the reply. The mic path is 16 kHz PCM from the INMP441 over I2S. Details: [Wiki → Firmware](https://github.com/kataro92/KatBot/wiki/Firmware).

## Protocol (device ↔ backend)

WebSocket: `ws://<pc>:8080/ws/device`

Text JSON (Xiaozhi-like) plus raw PCM binary frames (not Opus):

- Device `hello` / `listen` (`start` \| `stop`) / `telemetry` / `abort`
- Uplink binary: 16 kHz 16-bit mono PCM while listening
- Server `hello` (includes `session_id`, `listen_ms`) / `config` (`listen_ms`, ESP `volume`) / `listen` / `state` / `tts` (`start`, `sentence_start`, `stop`)
- Downlink binary: 16 kHz 16-bit mono PCM while speaking

Monitors use `ws://<pc>:8080/ws/monitor` and only receive fan-out events. See [Wiki → Protocol](https://github.com/kataro92/KatBot/wiki/Protocol).

## Security

- Do not commit `.env` or `firmware/KatBot/secrets.h`.
- Bind the backend to your LAN only; there is no auth on the WebSockets yet.
- Rotate any API keys copied from older projects. They are optional (ElevenLabs STT, Google CSE).

## Author

[Phạm Huy Đức](mailto:kataro92@gmail.com)

## License

[MIT](LICENSE) © 2026 Phạm Huy Đức

## Acknowledgments

- [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) for the session/transport ideas
- [Ollama](https://ollama.com/) for local LLM serving
