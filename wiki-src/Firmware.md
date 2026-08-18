# Firmware

Arduino sketch: `firmware/KatBot/KatBot.ino`  
Board: **NodeMCU 1.0 (ESP-12E)** — FQBN `esp8266:esp8266:nodemcuv2`

Compile with Arduino IDE or repo-root `compile.bat` (`arduino-cli`).

## Libraries

See `firmware/libraries.txt`:

- Adafruit SSD1306
- Adafruit GFX Library
- DHT sensor library
- Adafruit Unified Sensor
- ArduinoJson
- WebSockets (Markus Sattler / Links2004) — use a **2 KB** `MAX_DATA_SIZE` in `WebSockets.h` so PCM chunks fit

I2S uses the ESP8266 core `I2S.h` (no extra library).

## Secrets

Copy `firmware/KatBot/secrets.h.example` to `firmware/KatBot/secrets.h` (gitignored):

```c
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"
#define WS_HOST "192.168.x.x"   // PC LAN IPv4
#define WS_PORT 8080
```

`WS_HOST` must be the PC running `start.bat`, not `127.0.0.1` (the ESP cannot reach that).

## Listen button

- Pin `D6` / GPIO12, `INPUT_PULLUP`, press to GND
- **One press** starts a listen window (`LISTEN_MS` in `config.h`, overridable by backend `listen_ms`)
- Not hold-to-talk
- Ignored unless the device is `idle` and WebSocket is up
- OLED status: `nghe` + countdown → `nghi` → `noi` → `idle`

While listening, firmware samples **A0 at 8 kHz** and sends 16-bit PCM binary frames. It does not keep the full 5 s buffer in RAM.

## Speaker (I2S)

MAX98357: BCLK `D8`, LRC `D4`, DIN **RX / GPIO3** (native ESP8266 I2S data). Playback is 16 kHz 16-bit PCM from the backend. A short boot jingle plays after Wi-Fi.

No `Serial.begin` — RX is the amp data pin. Debug via OLED and the web monitor. USB upload still uses TX/RX in the bootloader before the sketch runs.

## OLED

128×64 SSD1306, chibi cat sprites in `cat_bitmaps.h` (regenerate with `firmware/tools/gen_cat_bitmaps.py` from `ref_cat.png`). Title bar shows DHT and mood (`wifi` / `idle` / `nghe` / `nghi` / `noi`).
