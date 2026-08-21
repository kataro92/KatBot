# Firmware

Arduino sketch: `firmware/KatBot/KatBot.ino`  
Board: **NodeMCU 1.0 (ESP-12E)** — FQBN `esp8266:esp8266:nodemcuv2`

Compile with Arduino IDE or repo-root `compile.bat` (`arduino-cli`).

## Libraries

See `firmware/libraries.txt`:

- Adafruit SSD1306
- Adafruit GFX Library
- ArduinoJson
- WebSockets (Markus Sattler / Links2004) — use a **2 KB** `MAX_DATA_SIZE` in `WebSockets.h` so PCM chunks fit

I2S uses the ESP8266 core `I2S.h` (no extra library).
DHT11 uses a project-local GPIO16-compatible reader because D0 has no internal pull-up.

## Build profiles and releases

The monitor's single firmware selector keeps profile and version together:

- **mic+loa `v0.2.x`** — INMP441 + MAX98357
- **chỉ mic `v0.1.x`** — speaker code is compiled out

Compile writes ESP8266 build flags through `KatBot.ino.globals.h`, performs a
clean build, and archives the binary and manifest under
`firmware/releases/<version>/`. The OLED title shows the compiled version.

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

- Pin `D3` / GPIO0, `INPUT_PULLUP`, press to GND (do not hold at boot)
- **One press** starts a listen window (`LISTEN_MS` in `config.h`, overridable by backend `listen_ms`)
- Not hold-to-talk
- Ignored unless the device is `idle` and WebSocket is up
- OLED status: `nghe` + countdown → `nghi` → `noi` → `idle`

While listening, firmware captures **INMP441 I2S at 16 kHz** and sends 16-bit PCM binary frames. It does not keep the full 5 s buffer in RAM.

## Mic (INMP441, I2S RX)

- `SCK` → `D7` / GPIO13 (`I2SI_BCK`)
- `WS` → `D5` / GPIO14 (`I2SI_WS`)
- `SD` → `D6` / GPIO12 (`I2SI_DATA` — **not** RX/GPIO3)
- `L/R` → `GND`
- CPU frequency should be **160 MHz**

Listen uses **RX-only** with native I2SI clocks. Speak (full build) uses separate I2SO pins for the amp — clocks are never shared with the mic.

## Speaker (I2S)

MAX98357 (mic+loa `v0.2.x`): BCLK `D8`, LRC `D4`, DIN **RX / GPIO3** (`I2SO_*`). Playback is 16 kHz 16-bit PCM from the backend. A short boot jingle plays after Wi-Fi.

Connect MAX98357 `SD` to 3V3 to keep the amp enabled; leave `GAIN` floating for
default gain. Playback volume is controlled by the monitor (0–100%, default
80%). No `Serial.begin` — RX is the amp data pin on full builds. Debug uses
OLED and the web monitor.

## DHT11 on D0

`DATA` connects to D0/GPIO16 and needs a **4.7–10 kΩ pull-up to 3V3**. GPIO16
does not implement `INPUT_PULLUP`, so the sketch drives the DHT11 transaction
with `INPUT` mode and verifies its checksum. The first read failure and recovery
are reported in the monitor log.

## OLED

128×64 SSD1306, chibi cat sprites in `cat_bitmaps.h` (regenerate with `firmware/tools/gen_cat_bitmaps.py` from `ref_cat.png`). Title bar shows DHT and mood (`wifi` / `idle` / `nghe` / `nghi` / `noi`).
