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
2. The ESP records **5 seconds** of **16 kHz I2S mic PCM** and sends it to the PC over Wi-Fi (WebSocket).
3. The PC normalizes quiet captures, runs STT, optional tools (weather / FX / search / multi-platform music), then Cursor CLI or Ollama, then TTS.
4. PCM plays on the selected ESP or PC speaker. The web monitor only connects to the PC — it does not load the ESP.

![Architecture](https://raw.githubusercontent.com/kataro92/KatBot/main/docs/architecture.png)

## Quick start

1. Install Python 3.12+ and [Ollama](https://ollama.com/) with a local model (`llama3.2` by default).
2. Clone the repo, double-click `start.bat`.
3. Open http://127.0.0.1:8080
4. Copy `firmware/KatBot/secrets.h.example` → `secrets.h`, set Wi-Fi and the PC LAN IP, then compile/flash the mic+speaker or mic-only profile from the monitor.

Current stage: the full talk loop is live with selectable ESP/PC audio routes,
ESP volume control, versioned firmware profiles, multi-platform music, a chibi
OLED UI, and a pastel glass monitor with SQLite history.
