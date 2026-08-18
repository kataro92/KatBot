# KatBot wiki

Local voice chatbot (**Mèo Bot**) on ESP-12F / NodeMCU. The chip is a thin client. Speech, LLM, tools, and the monitor run on your PC.

**Repository:** https://github.com/kataro92/KatBot  
**Author:** Phạm Huy Đức — kataro92@gmail.com  
**License:** MIT

## Pages

- [Hardware](Hardware) — modules, pin map, wiring, battery
- [Backend](Backend) — `start.bat`, STT, Cursor/Ollama, tools, monitor
- [Firmware](Firmware) — Arduino, `secrets.h`, listen window, OLED, I2S
- [Protocol](Protocol) — WebSocket JSON + PCM between ESP and PC

## How it fits together

1. You press the button on the NodeMCU.
2. The ESP records **5 seconds** of mic PCM and sends it to the PC over Wi-Fi (WebSocket).
3. The PC runs STT, optional tools (weather / FX / search / music), then Cursor CLI or Ollama, then TTS.
4. PCM comes back to the MAX98357. The web monitor only connects to the PC — it does not load the ESP.

![Architecture](https://raw.githubusercontent.com/kataro92/KatBot/main/docs/architecture.png)

## Quick start

1. Install Python 3.12+ and [Ollama](https://ollama.com/) with a local model (`llama3.2` by default).
2. Clone the repo, double-click `start.bat`.
3. Open http://127.0.0.1:8080
4. Copy `firmware/KatBot/secrets.h.example` → `secrets.h`, set Wi-Fi and the PC LAN IP, flash NodeMCU 1.0.

Current stage: full talk loop is live (listen → STT → tools/LLM → speaker), with a chibi OLED UI and a PC monitor.
