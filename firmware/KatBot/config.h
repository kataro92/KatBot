#pragma once

// NodeMCU v1.0 / ESP-12F  FQBN: esp8266:esp8266:nodemcuv2
// Use GPIO numbers (Dx aliases exist only on the NodeMCU board variant).

#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C
#define OLED_BAR_H 9

#define PIN_DHT 14          // D5
#define PIN_LISTEN_BTN 12   // D6, active LOW
#define PIN_I2S_BCLK 15     // D8 — MAX98357, later stage
#define PIN_I2S_LRC 2       // D4
#define PIN_I2S_DIN 3       // RX — native ESP8266 I2S data (no Serial)

#define DHT_TYPE DHT11
#define DHT_PERIOD_MS 8000
#define LISTEN_MS 5000
#define BTN_DEBOUNCE_MS 40
#define MIC_HZ 8000
#define MIC_CHUNK 160
#define PLAY_HZ 16000
// ~128 ms at 16 kHz. 512 samples (~32 ms) underrun → loa rè (EnvChatBot AMP_BUF 4KB).
#define PLAY_RING 2048
#define PLAY_PREFILL 1024
#define PLAY_GAIN_NUM 17
#define PLAY_GAIN_DEN 20

#define WS_PATH "/ws/device"
