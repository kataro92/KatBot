# KatBot (Mèo Bot)

Local voice chatbot on an **ESP-12F / NodeMCU**. The chip is a thin client; speech, LLM, and the web monitor run on your PC so the microcontroller stays light.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Wiki](https://img.shields.io/badge/docs-wiki-blue)](https://github.com/kataro92/KatBot/wiki)

![Kiến trúc KatBot](docs/architecture.png)

Inspired by [Xiaozhi](https://github.com/78/xiaozhi-esp32) (WebSocket session, listen/speak states), but fully local via [Ollama](https://ollama.com/). ESP-12F is an ESP8266 — this repo does **not** port Xiaozhi firmware (no ESP-SR wake word, no Opus, no AEC).

The browser talks only to the PC. It never loads the ESP.

**Docs:** [Wiki](https://github.com/kataro92/KatBot/wiki) · [Hardware & wiring](https://github.com/kataro92/KatBot/wiki/Hardware) · [Backend](https://github.com/kataro92/KatBot/wiki/Backend) · [Firmware](https://github.com/kataro92/KatBot/wiki/Firmware)

## Status

| Stage | What | State |
| --- | --- | --- |
| 0–1 | Backend, Ollama warm session, web monitor, Wi-Fi, OLED, DHT11, listen button (5 s) | Done |
| 2 | TTS playback over I2S (MAX98357) | Planned |
| 3 | Mic capture (MAX9814 → STT) | Planned |
| 4 | Full talk loop: 5 s listen → STT → Ollama → TTS | Planned |
| 5 | Reconnect polish, SFX, OLED emotion | Planned |

## Features (current)

- One warm Ollama chat session, reused by the device and the monitor test box
- System prompt: short, cute replies, no emoji, no extra explanation
- Press the button once → firmware opens a **5 second** listen window (not hold-to-talk)
- OLED status (`NGHE` countdown, `NGHI`, `NOI`) plus temperature / humidity
- Web dashboard: device online, DHT, listen bar, event log, text chat to test Ollama

Device states: `idle` → `listening` (5 s on the chip) → `thinking` → `speaking` → `idle`. Extra presses while busy are ignored (no barge-in in v1).

## Hardware

| Part | Role |
| --- | --- |
| ESP-12F on NodeMCU v1.0 | Wi-Fi MCU |
| SSD1306 0.96" I2C (e.g. JMD0.96D-1) | Display |
| MAX9814 | Analog mic (A0) |
| MAX98357 + 3 W speaker | I2S amp (wired in firmware; playback not yet) |
| DHT11 | Temperature / humidity |
| Momentary button | Listen trigger, active LOW |

No Arduino Uno coprocessor.

### Wiring

![Sơ đồ cắm dây KatBot](docs/wiring.png)

OLED JMD0.96D-1 pin order is commonly **GND–VCC–SCL–SDA**. If VCC/GND are swapped on the silkscreen, follow the PCB labels. Speaker wires go only to the MAX98357 `+` / `−` pads. Share GND. Power the amp from 5 V (`Vin`) for 3 W. Do not sample the ADC while I2S is playing.

Full pin notes: [Wiki → Hardware](https://github.com/kataro92/KatBot/wiki/Hardware).

### Pin map (NodeMCU labels)

| Function | Pin | GPIO | Notes |
| --- | --- | --- | --- |
| OLED SDA | D2 | 4 | Default Wire |
| OLED SCL | D1 | 5 | Default Wire |
| DHT11 | D5 | 14 | |
| Listen button | D6 | 12 | Internal pull-up, press to GND |
| MAX9814 OUT | A0 | ADC | NodeMCU divider, 0–3.3 V |
| MAX98357 BCLK | D8 | 15 | Must be LOW at boot |
| MAX98357 LRC | D4 | 2 | |
| MAX98357 DIN | RX | 3 | Native I2S data; no Serial debug |

## Repository layout

```
KatBot/
  start.bat         Start backend (venv + deps + server)
  backend/          FastAPI (device WS, monitor WS, Ollama)
  firmware/KatBot/  Arduino sketch for NodeMCU
  web/              Monitor UI (served by the backend)
  docs/             Architecture and wiring diagrams
  wiki-src/         GitHub Wiki source
  .env.example      Backend settings (no secrets)
  LICENSE           MIT
```

## Requirements

**PC:** Python 3.12+, [Ollama](https://ollama.com/) with a local model (default `llama3.2`), same LAN as the NodeMCU.

**Firmware:** Arduino IDE or arduino-cli, ESP8266 core, board **NodeMCU 1.0 (ESP-12E)** (`esp8266:esp8266:nodemcuv2`). Libraries: see [`firmware/libraries.txt`](firmware/libraries.txt) (Adafruit SSD1306, Adafruit GFX, DHT sensor library, Adafruit Unified Sensor, ArduinoJson, WebSockets).

## Quick start

### 1. Backend

Double-click [`start.bat`](start.bat) in the repo root. It creates `backend/.venv` if needed, installs missing packages, copies `.env` from `.env.example` when absent, then starts the server.

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) (or `http://<pc-lan-ip>:8080`). Use the text box to confirm Ollama before flashing.

Ollama must already be running. On startup the backend preloads the model (`keep_alive=-1`) and keeps one chat history.

Useful env vars (repo-root `.env`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address (`0.0.0.0` so the ESP can connect) |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API |
| `OLLAMA_MODEL` | `llama3.2` | Any local model you already pulled |
| `OLLAMA_KEEP_ALIVE` | `-1` | Keep the model loaded |
| `OLLAMA_NUM_PREDICT` | `80` | Short replies |

`STT_*` and `TTS_*` are reserved for later stages. More: [Wiki → Backend](https://github.com/kataro92/KatBot/wiki/Backend).

### 2. Firmware

1. Copy [`firmware/KatBot/secrets.h.example`](firmware/KatBot/secrets.h.example) to `firmware/KatBot/secrets.h`.
2. Set `WIFI_SSID`, `WIFI_PASS`, and `WS_HOST` to this PC’s LAN IPv4. `secrets.h` is gitignored.
3. Select **NodeMCU 1.0 (ESP-12E)**, the correct COM port, 115200 baud.
4. Upload [`firmware/KatBot/KatBot.ino`](firmware/KatBot/KatBot.ino).
5. OLED: Wi-Fi then `san sang` when the WebSocket is up. The dashboard should show **ESP online**.

Press the listen button once (do not hold). OLED shows `NGHE` and a countdown; after 5 s it shows `NGHI` until the backend returns `idle`. Microphone streaming is not enabled yet.

Details: [Wiki → Firmware](https://github.com/kataro92/KatBot/wiki/Firmware).

## Protocol (device ↔ backend)

WebSocket: `ws://<pc>:8080/ws/device`

Text JSON (Xiaozhi-like, PCM later instead of Opus):

- Device `hello` / `listen` (`start` \| `stop`) / `telemetry` / `abort`
- Server `hello` (includes `session_id`) / `state` / `stt` / `tts` (later)

Monitors use `ws://<pc>:8080/ws/monitor` and only receive fan-out events. See [Wiki → Protocol](https://github.com/kataro92/KatBot/wiki/Protocol).

## Security

- Do not commit `.env` or `firmware/KatBot/secrets.h`.
- Bind the backend to your LAN only; there is no auth on the WebSockets yet.
- Rotate any API keys copied from older projects; they are not required for the Ollama path.

## Roadmap

See the status table. Next: I2S TTS downlink, then 8 kHz PCM uplink and PhoWhisper / gTTS from `.env.example`.

## Author

[Phạm Huy Đức](mailto:kataro92@gmail.com)

## License

[MIT](LICENSE) © 2026 Phạm Huy Đức

## Acknowledgments

- [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) for the session/transport ideas
- [Ollama](https://ollama.com/) for local LLM serving
