#pragma once

// NodeMCU v1.0 / ESP-12F  FQBN: esp8266:esp8266:nodemcuv2

#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C

#define PIN_DHT D5          // GPIO14
#define PIN_LISTEN_BTN D6   // GPIO12, active LOW
#define PIN_I2S_BCLK D8     // GPIO15 — MAX98357, later stage
#define PIN_I2S_LRC D4      // GPIO2
#define PIN_I2S_DIN D7      // GPIO13

#define DHT_TYPE DHT11
#define DHT_PERIOD_MS 8000
#define LISTEN_MS 5000
#define BTN_DEBOUNCE_MS 40

#define WS_PATH "/ws/device"
