#pragma once

// NodeMCU v1.0 / ESP-12F  FQBN: esp8266:esp8266:nodemcuv2
// Use GPIO numbers (Dx aliases exist only on the NodeMCU board variant).

// Semver of this sketch (full = mic+loa). Override via globals.h for profiles.
#ifndef FW_VERSION
#define FW_VERSION "0.2.3"
#endif

// 1 = MAX98357 TTS/jingle; 0 = mic-only build (profile mic → FW 0.1.x).
#ifndef KATBOT_HAVE_SPEAKER
#define KATBOT_HAVE_SPEAKER 1
#endif

#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C
#define OLED_TITLE_H 11

// ── Shared pin map (mic uses native I2SI_*; amp uses I2SO_* when present) ──
// Mic:  SD=D6/GPIO12, SCK=D7/GPIO13, WS=D5/GPIO14
// Amp:  DIN=RX/GPIO3, BCLK=D8/GPIO15, LRC=D4/GPIO2  (full only)
// Btn:  D3/GPIO0  ·  DHT: D0/GPIO16  ·  OLED: D1/D2

#define PIN_I2S_MIC_SD 12   // D6 — I2SI_DATA
#define PIN_I2S_MIC_SCK 13  // D7 — I2SI_BCK
#define PIN_I2S_MIC_WS 14   // D5 — I2SI_WS
#define PIN_LISTEN_BTN 0    // D3, active LOW (avoid D4/D5/D7 — I2S)
#define PIN_DHT 16          // D0 — requires external 4.7k-10k pull-up to 3V3

#if KATBOT_HAVE_SPEAKER
#define PIN_I2S_DIN 3       // RX — amp DIN (I2SO_DATA)
#define PIN_I2S_AMP_BCLK 15 // D8 — I2SO_BCK
#define PIN_I2S_AMP_LRC 2   // D4 — I2SO_WS
#endif

#define MIC_GAIN 4

#define DHT_PERIOD_MS 8000
#define LISTEN_MS 5000
#define BTN_DEBOUNCE_MS 40
#define MIC_HZ 16000
#define MIC_CHUNK 320        // 20 ms at 16 kHz
#define MIC_I2S_BITS 16      // Philips 16-bit stereo slots; INMP441 MSBs in left
#define MIC_SETTLE_SAMPLES 800  // ~50 ms discard after I2S start
#define PLAY_HZ 16000
// ~128 ms at 16 kHz. 512 samples (~32 ms) underrun → loa rè (EnvChatBot AMP_BUF 4KB).
#define PLAY_RING 2048
#define PLAY_PREFILL 1024
#define PLAY_VOLUME_DEFAULT 80

#define WS_PATH "/ws/device"

struct ToneNote {
  uint16_t hz;
  uint16_t ms;
};
