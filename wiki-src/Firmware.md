# Firmware

Arduino sketch: `firmware/KatBot/KatBot.ino`  
Board: **NodeMCU 1.0 (ESP-12E)** — FQBN `esp8266:esp8266:nodemcuv2`

## Libraries

See `firmware/libraries.txt`:

- Adafruit SSD1306
- Adafruit GFX Library
- DHT sensor library
- Adafruit Unified Sensor
- ArduinoJson
- WebSockets (Markus Sattler / Links2004)

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
- **One press** starts a **5 second** window (`LISTEN_MS` in `config.h`)
- Not hold-to-talk
- Ignored unless the device is `idle` and WebSocket is up
- OLED: `NGHE` + countdown → `NGHI` until the backend sends `idle`

Mic PCM and I2S playback are not enabled yet; listen start/stop and telemetry already go to the PC.

No `Serial.begin` — RX (GPIO3) is reserved for MAX98357 DIN (hardware I2S). Debug via OLED and the web monitor. USB upload still uses TX/RX in the bootloader before the sketch runs.
