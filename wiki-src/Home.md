# KatBot wiki

Local voice chatbot (**Mèo Bot**) on ESP-12F / NodeMCU. The chip is a thin client. Speech, LLM, and the monitor run on your PC.

**Repository:** https://github.com/kataro92/KatBot  
**Author:** Phạm Huy Đức — kataro92@gmail.com  
**License:** MIT

## Pages

- [Hardware](Hardware) — modules, pin map, wiring diagram
- [Backend](Backend) — `start.bat`, Ollama, monitor
- [Firmware](Firmware) — Arduino, `secrets.h`, listen 5 s
- [Protocol](Protocol) — WebSocket JSON between ESP and PC

## How it fits together

1. You press the button on the NodeMCU.
2. The ESP listens for **5 seconds** and talks to the PC over Wi-Fi (WebSocket).
3. The PC runs Ollama (and later STT/TTS).
4. The web monitor only connects to the PC — it does not load the ESP.

![Architecture](https://raw.githubusercontent.com/kataro92/KatBot/main/docs/architecture.png)

## Quick start

1. Install Python 3.12+ and [Ollama](https://ollama.com/) with a local model (`llama3.2` by default).
2. Clone the repo, double-click `start.bat`.
3. Open http://127.0.0.1:8080
4. Copy `firmware/KatBot/secrets.h.example` → `secrets.h`, set Wi-Fi and the PC LAN IP, flash NodeMCU 1.0.

Current stage: telemetry, OLED, DHT, 5 s button, Ollama test chat. Mic/speaker pipeline is next.
