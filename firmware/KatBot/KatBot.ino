#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WebSocketsClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <I2S.h>
#include <user_interface.h>

#include "config.h"
#include "secrets.h"
#include "cat_ui.h"

enum DeviceState : uint8_t {
  ST_BOOT = 0,
  ST_WIFI,
  ST_IDLE,
  ST_LISTENING,
  ST_THINKING,
  ST_SPEAKING
};

static Adafruit_SSD1306 oled(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
static WebSocketsClient webSocket;

static DeviceState gState = ST_BOOT;
static bool oledOk = false;
static bool wsReady = false;
static char sessionId[16] = "";
static float lastTemp = NAN;
static float lastHum = NAN;
static uint32_t lastDhtMs = 0;
static uint32_t listenStartMs = 0;
static uint32_t listenWindowMs = LISTEN_MS;
static uint32_t lastOledMs = 0;
static uint8_t btnPrev = HIGH;
static uint32_t btnChangeMs = 0;

static char txbuf[256];
static char rxbuf[384];

static int16_t micBuf[MIC_CHUNK];
static uint16_t micCount = 0;
static uint32_t micSamples = 0;
static uint32_t micChunks = 0;
static uint32_t micEmpty = 0;
static int16_t micPeak = 0;
static uint32_t lastMicDbgMs = 0;
static bool micNeedFirstLog = false;
static bool micBitsOk = false;
static uint32_t micAbsL = 0;
static uint32_t micAbsR = 0;
static uint16_t micPickN = 0;
static int8_t micSlot = 0;  // 0 = left (INMP441 L/R=GND), 1 = right if core swaps
static bool micNeedSlotLog = false;

#if KATBOT_HAVE_SPEAKER
static char speakLine[22] = "";
static int16_t playRing[PLAY_RING];
static uint16_t playW = 0;
static uint16_t playR = 0;
static bool i2sOn = false;
static bool playDraining = false;
static bool bootSinging = false;
static const char* sfxLabel = nullptr;
static uint8_t playVolume = PLAY_VOLUME_DEFAULT;
#endif

static const char* stateName(DeviceState s) {
  switch (s) {
    case ST_WIFI: return "wifi";
    case ST_IDLE: return "idle";
    case ST_LISTENING: return "listening";
    case ST_THINKING: return "thinking";
    case ST_SPEAKING: return "speaking";
    default: return "boot";
  }
}

static CatMood moodFromState() {
  switch (gState) {
    case ST_LISTENING:
      return CAT_LISTEN;
    case ST_THINKING:
      return CAT_THINK;
    case ST_SPEAKING:
      return CAT_SPEAK;
    case ST_IDLE:
      return CAT_IDLE;
    default:
      return CAT_WIFI;
  }
}

static void renderOled() {
  if (!oledOk) return;
  lastOledMs = millis();
#if KATBOT_HAVE_SPEAKER
  CatMood mood = (bootSinging || sfxLabel) ? CAT_SPEAK : moodFromState();
#else
  CatMood mood = moodFromState();
#endif
  catUiTick(lastOledMs, mood);

  char left[18];
  char right[10];
  left[0] = wsReady ? '*' : '-';
  left[1] = ' ';
  if (!isnan(lastTemp) && !isnan(lastHum)) {
    snprintf_P(left + 2, sizeof(left) - 2, PSTR("%.0fC %.0f%%"), lastTemp, lastHum);
  } else {
    snprintf_P(left + 2, sizeof(left) - 2, PSTR("Meo"));
  }

#if KATBOT_HAVE_SPEAKER
  if (sfxLabel) {
    snprintf_P(right, sizeof(right), PSTR("%s"), sfxLabel);
  } else if (bootSinging) {
    snprintf_P(right, sizeof(right), PSTR("hello"));
  } else if (gState == ST_LISTENING) {
#else
  if (gState == ST_LISTENING) {
#endif
    uint32_t leftSec = 0;
    uint32_t elapsed = millis() - listenStartMs;
    if (elapsed < listenWindowMs) leftSec = (listenWindowMs - elapsed + 999) / 1000;
    snprintf_P(right, sizeof(right), PSTR("nghe %lu"), (unsigned long)leftSec);
  } else if (gState == ST_THINKING) {
    snprintf_P(right, sizeof(right), PSTR("nghi"));
  } else if (gState == ST_SPEAKING) {
    snprintf_P(right, sizeof(right), PSTR("noi"));
  } else if (gState == ST_WIFI || gState == ST_BOOT) {
    snprintf_P(right, sizeof(right), PSTR("wifi"));
  } else {
    snprintf_P(right, sizeof(right), PSTR("idle"));
  }

  uint8_t progress = 255;
  if (gState == ST_LISTENING && listenWindowMs > 0) {
    uint32_t elapsed = millis() - listenStartMs;
    if (elapsed > listenWindowMs) elapsed = listenWindowMs;
    progress = (uint8_t)((elapsed * 100UL) / listenWindowMs);
  }

  catDraw(oled, mood, left, right, progress);
  oled.display();
}

#if KATBOT_HAVE_SPEAKER
static bool beginPlayI2s() {
  i2s_end();
  I2S.end();
  i2sOn = false;
  // MAX98357 needs 16-bit Philips (BCLK = 32× LRCLK).
  if (!i2s_set_bits(16)) {
    i2s_end();
    I2S.end();
    i2s_set_bits(16);
  }
  // TX-only on I2SO_* (DIN=RX, BCLK=D8, LRC=D4). I2S.begin keeps wrapper _running
  // so availableForWrite()/end() stay in sync for TTS pumpPlay.
  if (!I2S.begin(I2S_PHILIPS_MODE, PLAY_HZ, 16)) {
    // Fallback if wrapper thought it was still running
    I2S.end();
    i2s_end();
    if (!i2s_set_bits(16)) i2s_set_bits(16);
    if (!i2s_rxtxdrive_begin(false, true, false, true)) {
      return false;
    }
    i2s_set_rate(PLAY_HZ);
    // Wrapper may still be !_running — pumpPlay uses i2s_available() as well.
  }
  i2sOn = true;
  return true;
}

static void playToneSong(const ToneNote* song, uint8_t nNotes, const char* label) {
  sfxLabel = label;
  renderOled();
  if (!beginPlayI2s()) {
    sfxLabel = nullptr;
    renderOled();
    return;
  }
  i2sOn = true;
  int16_t buf[64];
  uint32_t lastFrame = millis();
  for (uint8_t n = 0; n < nNotes; n++) {
    ToneNote note;
    memcpy_P(&note, &song[n], sizeof(ToneNote));
    uint32_t samples = ((uint32_t)PLAY_HZ * note.ms) / 1000UL;
    uint16_t half = 0;
    if (note.hz >= 40) {
      half = (uint16_t)(PLAY_HZ / (note.hz * 2U));
      if (half < 2) half = 2;
    }
    uint16_t phase = 0;
    int16_t amp = (int16_t)((7800L * playVolume) / 100L);
    int16_t s = amp;
    uint32_t fade = PLAY_HZ / 90;
    uint32_t i = 0;
    while (i < samples) {
      uint8_t chunk = 64;
      if (samples - i < 64) chunk = (uint8_t)(samples - i);
      for (uint8_t k = 0; k < chunk; k++, i++) {
        int16_t v = 0;
        if (half) {
          if (phase == 0) s = (int16_t)-s;
          phase++;
          if (phase >= half) phase = 0;
          v = s;
          if (i < fade) v = (int16_t)((int32_t)v * (int32_t)i / (int32_t)fade);
          uint32_t rem = samples - i;
          if (rem < fade) v = (int16_t)((int32_t)v * (int32_t)rem / (int32_t)fade);
        }
        buf[k] = v;
      }
      uint8_t off = 0;
      while (off < chunk) {
        uint16_t w = i2s_write_buffer_mono(buf + off, chunk - off);
        if (w == 0) {
          yield();
          continue;
        }
        off = (uint8_t)(off + w);
      }
      uint32_t now = millis();
      if (now - lastFrame >= 280) {
        lastFrame = now;
        renderOled();
      }
      yield();
    }
  }
  int16_t z[32] = {0};
  i2s_write_buffer_mono(z, 32);
  I2S.end();
  i2s_end();
  i2sOn = false;
  playDraining = false;
  playW = 0;
  playR = 0;
  sfxLabel = nullptr;
}

static void playBootJingle() {
  static const ToneNote song[] PROGMEM = {
      {659, 160}, {784, 160}, {1047, 160}, {1319, 320}, {0, 140},
      {1047, 160}, {784, 160}, {659, 320},  {0, 140},
      {1319, 160}, {1568, 160}, {2093, 420},
  };
  bootSinging = true;
  playToneSong(song, sizeof(song) / sizeof(song[0]), "hello");
  bootSinging = false;
}

static void playMeo() {
  static const ToneNote song[] PROGMEM = {
      {740, 55}, {880, 70}, {1175, 85}, {988, 55}, {659, 130}, {0, 30},
  };
  playToneSong(song, sizeof(song) / sizeof(song[0]), "meo");
}

static void playMeoMeo() {
  static const ToneNote song[] PROGMEM = {
      {740, 50}, {880, 65}, {1175, 80}, {988, 50}, {659, 110}, {0, 90},
      {740, 50}, {880, 65}, {1245, 85}, {988, 55}, {622, 140}, {0, 30},
  };
  playToneSong(song, sizeof(song) / sizeof(song[0]), "meo");
}
#endif

static void applyListenMs(int ms) {
  if (ms < 1000) ms = 1000;
  if (ms > 60000) ms = 60000;
  listenWindowMs = (uint32_t)ms;
}

static void sendTxt() {
  if (!wsReady) return;
  webSocket.sendTXT(txbuf);
}

static void sendLogLv(const char* level, const char* msg) {
  snprintf_P(
      txbuf,
      sizeof(txbuf),
      PSTR("{\"type\":\"log\",\"level\":\"%s\",\"message\":\"%s\"}"),
      level,
      msg);
  sendTxt();
}

static void sendLog(const char* msg) {
  sendLogLv("info", msg);
}

static void sendHello() {
  snprintf_P(
      txbuf,
      sizeof(txbuf),
      PSTR("{\"type\":\"hello\",\"version\":1,\"fw_version\":\"%s\",\"speaker\":%s,"
           "\"transport\":\"websocket\","
           "\"audio_params\":{\"format\":\"pcm\",\"sample_rate\":16000,\"channels\":1,\"bits\":16}}"),
      FW_VERSION,
      KATBOT_HAVE_SPEAKER ? "true" : "false");
  sendTxt();
}

static void sendListen(const char* listenState) {
  snprintf_P(
      txbuf,
      sizeof(txbuf),
      PSTR("{\"type\":\"listen\",\"state\":\"%s\",\"mode\":\"manual\"}"),
      listenState);
  sendTxt();
}

static void sendTelemetry() {
  if (!wsReady) return;
  if (isnan(lastTemp) || isnan(lastHum)) {
    snprintf_P(
        txbuf,
        sizeof(txbuf),
        PSTR("{\"type\":\"telemetry\",\"state\":\"%s\",\"listen_ms\":%lu}"),
        stateName(gState),
        (unsigned long)listenWindowMs);
  } else {
    snprintf_P(
        txbuf,
        sizeof(txbuf),
        PSTR("{\"type\":\"telemetry\",\"temp\":%.1f,\"humidity\":%.0f,\"state\":\"%s\",\"listen_ms\":%lu}"),
        lastTemp,
        lastHum,
        stateName(gState),
        (unsigned long)listenWindowMs);
  }
  sendTxt();
}

static void setState(DeviceState s) {
  if (gState == s) return;
  gState = s;
  sendTelemetry();
  renderOled();
}

#if KATBOT_HAVE_SPEAKER
static uint16_t playCount() {
  return (uint16_t)((playW + PLAY_RING - playR) % PLAY_RING);
}

static uint16_t playSpace() {
  return (uint16_t)((playR + PLAY_RING - playW - 1) % PLAY_RING);
}

static void ensureI2s();
static void pumpPlay();

static void playPush(const uint8_t* data, size_t len) {
  size_t n = len / 2;
  for (size_t i = 0; i < n; i++) {
    if (playSpace() == 0) {
      pumpPlay();
      if (playSpace() == 0) break;
    }
    int16_t s;
    memcpy(&s, data + (i * 2), 2);
    int32_t v = ((int32_t)s * playVolume) / 100L;
    if (v > 24000) v = 24000 + (v - 24000) / 4;
    if (v < -24000) v = -24000 + (v + 24000) / 4;
    if (v > 32767) v = 32767;
    if (v < -32767) v = -32767;
    playRing[playW] = (int16_t)v;
    playW = (uint16_t)((playW + 1) % PLAY_RING);
  }
  if (!i2sOn && !playDraining && playCount() >= PLAY_PREFILL) {
    ensureI2s();
  }
}

static void ensureI2s() {
  if (i2sOn) return;
  if (!beginPlayI2s()) return;
  int16_t z[32] = {0};
  i2s_write_buffer_mono_nb(z, 32);
}

static void stopI2s() {
  if (i2sOn) {
    int16_t z[32] = {0};
    i2s_write_buffer_mono_nb(z, 32);
    I2S.end();
  }
  i2sOn = false;
  playDraining = false;
  playW = 0;
  playR = 0;
}

static void pumpPlay() {
  if (!i2sOn) {
    if (playDraining && playCount() == 0) {
      playDraining = false;
      speakLine[0] = 0;
      setState(ST_IDLE);
    }
    return;
  }
  while (playR != playW) {
    // Prefer core queue; I2S.availableForWrite() is 0 if wrapper !_running.
    uint16_t avail = (uint16_t)i2s_available();
    if (avail == 0) {
      avail = (uint16_t)I2S.availableForWrite();
    }
    if (avail == 0) break;
    uint16_t contig = (playW > playR) ? (uint16_t)(playW - playR) : (uint16_t)(PLAY_RING - playR);
    if (contig > avail) contig = avail;
    uint16_t n = i2s_write_buffer_mono_nb(&playRing[playR], contig);
    if (n == 0) break;
    playR = (uint16_t)((playR + n) % PLAY_RING);
  }
  if (playDraining && playR == playW) {
    stopI2s();
    speakLine[0] = 0;
    setState(ST_IDLE);
  }
}
#else
static void stopI2s() {}
static void pumpPlay() {}
#endif

// ── INMP441 I2S mic ──────────────────────────────────────────────────────────
// Native RX pins (I2SI_*): SD=D6, SCK=D7, WS=D5. Amp (if any) uses separate
// TX pins (I2SO_*): DIN=RX, BCLK=D8, LRC=D4 — never share clocks with the mic.

static bool micI2sBegin() {
  i2s_end();
  I2S.end();
#if KATBOT_HAVE_SPEAKER
  i2sOn = false;
  playDraining = false;
  playW = 0;
  playR = 0;
#endif
  micBitsOk = i2s_set_bits(MIC_I2S_BITS);
  if (!micBitsOk) {
    sendLogLv("warn", "mic i2s_set_bits FAIL");
  }
  // RX-only + drive I2SI clocks. TX off while listening (no underrun / bus fight).
  bool ok = i2s_rxtxdrive_begin(true, false, true, false);
  i2s_set_rate(MIC_HZ);
  int16_t l = 0, r = 0;
  for (uint16_t i = 0; i < MIC_SETTLE_SAMPLES; i++) {
    if (!i2s_read_sample(&l, &r, true)) break;
    if ((i & 63) == 0) yield();
  }
  return ok;
}

static void micI2sStop() {
  i2s_end();
  I2S.end();
}

static void flushMic() {
  if (micCount > 0 && wsReady) {
    webSocket.sendBIN((uint8_t*)micBuf, micCount * 2);
    micChunks++;
    micCount = 0;
  }
}

static void micFeedSilence() {
  // TX is off during listen; nothing to feed.
}

static int16_t micUnpack(int16_t left, int16_t right) {
  // L/R=GND → left channel; right is usually empty noise on ESP8266 RX.
  (void)right;
  int16_t raw = left;
  int32_t v = (int32_t)raw * MIC_GAIN;
  if (v > 32767) v = 32767;
  if (v < -32767) v = -32767;
  return (int16_t)v;
}

static void sampleMic() {
  if (gState != ST_LISTENING) return;
  uint8_t n = 0;
  int16_t firstL = 0, firstR = 0, firstS = 0;
  bool got = false;
  while (n < 64) {
    int16_t left = 0, right = 0;
    if (!i2s_read_sample(&left, &right, false)) break;
    int16_t s = micUnpack(left, right);
    if (!got) {
      firstL = left;
      firstR = right;
      firstS = s;
      got = true;
    }
    int16_t a = s < 0 ? (int16_t)-s : s;
    if (a > micPeak) micPeak = a;
    micBuf[micCount++] = s;
    micSamples++;
    n++;
    if (micCount >= MIC_CHUNK) {
      if (wsReady) {
        webSocket.sendBIN((uint8_t*)micBuf, MIC_CHUNK * 2);
      } else {
        sendLogLv("warn", "mic BIN skip ws=0");
      }
      micChunks++;
      micCount = 0;
    }
  }
  if (n == 0) {
    micEmpty++;
  } else if (micNeedFirstLog) {
    micNeedFirstLog = false;
    char line[88];
    snprintf_P(
        line,
        sizeof(line),
        PSTR("mic first L=%d R=%d s=%d n=%u rxq=%u txq=%u"),
        (int)firstL,
        (int)firstR,
        (int)firstS,
        (unsigned)n,
        (unsigned)i2s_rx_available(),
        (unsigned)i2s_available());
    sendLogLv("debug", line);
  }
  if (micNeedSlotLog) {
    micNeedSlotLog = false;
    char line[80];
    snprintf_P(
        line,
        sizeof(line),
        PSTR("mic slot=%c sumL=%lu sumR=%lu"),
        micSlot ? 'R' : 'L',
        (unsigned long)micAbsL,
        (unsigned long)micAbsR);
    sendLogLv("debug", line);
  }
  micFeedSilence();
}

static void startListen() {
  if (!wsReady) {
    return;
  }
  if (gState != ST_IDLE) {
    char line[48];
    snprintf_P(line, sizeof(line), PSTR("mic skip state=%s"), stateName(gState));
    sendLogLv("warn", line);
    return;
  }
  int sdBefore = digitalRead(PIN_I2S_MIC_SD);
  int btnNow = digitalRead(PIN_LISTEN_BTN);
  stopI2s();
#if KATBOT_HAVE_SPEAKER
  playMeo();            // playMeo uses TX I2S; ends before we start RX
#endif
  listenStartMs = millis();
  lastMicDbgMs = listenStartMs;
  micCount = 0;
  micSamples = 0;
  micChunks = 0;
  micEmpty = 0;
  micPeak = 0;
  micNeedFirstLog = true;
  micAbsL = 0;
  micAbsR = 0;
  micPickN = 0;
  micSlot = 0;
  micNeedSlotLog = false;
  bool i2sOk = micI2sBegin();
  {
    char line[120];
    snprintf_P(
        line,
        sizeof(line),
        PSTR("mic I2S %s RX-only bits=%u SD=D6 SCK=D7 WS=D5 hz=%u gain=%u win=%lums cpu=%u btn=%d rxq=%u"),
        i2sOk ? "ok" : "FAIL",
        (unsigned)MIC_I2S_BITS,
        (unsigned)MIC_HZ,
        (unsigned)MIC_GAIN,
        (unsigned long)listenWindowMs,
        (unsigned)system_get_cpu_freq(),
        btnNow,
        (unsigned)i2s_rx_available());
    (void)sdBefore;
    sendLogLv(i2sOk ? "info" : "warn", line);
  }
  gState = ST_LISTENING;
  sendListen("start");
  sendTelemetry();
  renderOled();
}

static void finishListen() {
  flushMic();
  {
    char line[96];
    snprintf_P(
        line,
        sizeof(line),
        PSTR("mic stop n=%lu peak=%d chunks=%lu empty=%lu slot=%c rxq=%u"),
        (unsigned long)micSamples,
        (int)micPeak,
        (unsigned long)micChunks,
        (unsigned long)micEmpty,
        micSlot ? 'R' : 'L',
        (unsigned)i2s_rx_available());
    sendLogLv("info", line);
  }
  micI2sStop();         // release I2S RX before switching back to TX
  gState = ST_THINKING;
  sendListen("stop");
  sendTelemetry();
  renderOled();
#if KATBOT_HAVE_SPEAKER
  playMeoMeo();         // TX I2S re-initialised inside playMeoMeo → ensureI2s
  renderOled();
#endif
}

static void handleButton() {
  uint8_t now = digitalRead(PIN_LISTEN_BTN);
  uint32_t t = millis();
  if (now != btnPrev) {
    btnChangeMs = t;
    btnPrev = now;
  }
  if ((t - btnChangeMs) < BTN_DEBOUNCE_MS) return;
  static uint8_t stable = HIGH;
  if (now == stable) return;
  stable = now;
  if (stable == LOW) {
    startListen();
  }
}

// GPIO16/D0 has no internal pull-up. Adafruit DHT's INPUT_PULLUP leaves this
// special pin in OUTPUT mode after its start pulse, so read DHT11 directly
// with INPUT mode and an external 4.7k-10k DATA-to-3V3 pull-up.
static bool dhtWaitForLevel(uint8_t level, uint32_t timeoutUs) {
  uint32_t started = micros();
  while ((uint8_t)digitalRead(PIN_DHT) != level) {
    if ((uint32_t)(micros() - started) >= timeoutUs) return false;
  }
  return true;
}

static bool readDht11Gpio16(float& humidity, float& temperature) {
  uint8_t data[5] = {0, 0, 0, 0, 0};

  pinMode(PIN_DHT, INPUT);
  delay(1);
  pinMode(PIN_DHT, OUTPUT);
  digitalWrite(PIN_DHT, LOW);
  delay(20);
  pinMode(PIN_DHT, INPUT);  // External resistor releases DATA high.
  delayMicroseconds(30);

  bool timingOk = true;
  noInterrupts();
  do {
    // DHT11 response: ~80 us LOW, ~80 us HIGH.
    if (!dhtWaitForLevel(LOW, 100)) {
      timingOk = false;
      break;
    }
    if (!dhtWaitForLevel(HIGH, 120)) {
      timingOk = false;
      break;
    }
    if (!dhtWaitForLevel(LOW, 120)) {
      timingOk = false;
      break;
    }

    // Each bit starts LOW, then HIGH for ~26 us (0) or ~70 us (1).
    for (uint8_t bit = 0; bit < 40; bit++) {
      if (!dhtWaitForLevel(HIGH, 100)) {
        timingOk = false;
        break;
      }
      uint32_t highStarted = micros();
      if (!dhtWaitForLevel(LOW, 120)) {
        timingOk = false;
        break;
      }
      data[bit / 8] <<= 1;
      if ((uint32_t)(micros() - highStarted) > 40) {
        data[bit / 8] |= 1;
      }
    }
  } while (false);
  interrupts();

  pinMode(PIN_DHT, INPUT);
  if (!timingOk) return false;
  if (data[4] != (uint8_t)(data[0] + data[1] + data[2] + data[3])) {
    return false;
  }

  humidity = data[0] + data[1] * 0.1f;
  temperature = data[2] + (data[3] & 0x0f) * 0.1f;
  if (data[3] & 0x80) temperature = -temperature;
  return true;
}

static void maybeDht() {
  if (gState != ST_IDLE) return;
  uint32_t t = millis();
  if (t - lastDhtMs < DHT_PERIOD_MS && lastDhtMs != 0) return;
  lastDhtMs = t;
  float h = NAN;
  float temp = NAN;
  static bool failureLogged = false;
  if (!readDht11Gpio16(h, temp)) {
    if (!failureLogged) {
      sendLog("DHT11 D0 fail: kiem tra pull-up DATA-3V3");
      failureLogged = true;
    }
    return;
  }
  if (failureLogged) sendLog("DHT11 D0 da doc lai duoc");
  failureLogged = false;
  lastHum = h;
  lastTemp = temp;
  sendTelemetry();
  renderOled();
}

static void onJson(const char* json) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) return;
  const char* type = doc["type"];
  if (!type) return;

  if (strcmp(type, "hello") == 0) {
    const char* sid = doc["session_id"];
    if (sid) {
      strncpy(sessionId, sid, sizeof(sessionId) - 1);
      sessionId[sizeof(sessionId) - 1] = 0;
    }
    if (!doc["listen_ms"].isNull()) {
      applyListenMs(doc["listen_ms"].as<int>());
    }
    wsReady = true;
    setState(ST_IDLE);
    sendTelemetry();
  } else if (strcmp(type, "config") == 0) {
    if (!doc["listen_ms"].isNull()) {
      applyListenMs(doc["listen_ms"].as<int>());
    }
#if KATBOT_HAVE_SPEAKER
    if (!doc["volume"].isNull()) {
      int volume = doc["volume"].as<int>();
      if (volume < 0) volume = 0;
      if (volume > 100) volume = 100;
      playVolume = (uint8_t)volume;
      char line[32];
      snprintf_P(line, sizeof(line), PSTR("loa volume=%u%%"), (unsigned)playVolume);
      sendLog(line);
    }
#endif
  } else if (strcmp(type, "listen") == 0) {
    // Remote start from web monitor (Micro = ESP).
    const char* listenState = doc["state"];
    if (listenState && strcmp(listenState, "start") == 0) {
      startListen();
    }
  } else if (strcmp(type, "state") == 0) {
    const char* value = doc["value"];
    if (value && strcmp(value, "idle") == 0) {
      stopI2s();
#if KATBOT_HAVE_SPEAKER
      speakLine[0] = 0;
#endif
      setState(ST_IDLE);
    }
#if KATBOT_HAVE_SPEAKER
  } else if (strcmp(type, "tts") == 0) {
    const char* ttsState = doc["state"];
    if (!ttsState) return;
    if (strcmp(ttsState, "start") == 0) {
      stopI2s();
      playDraining = false;
      setState(ST_SPEAKING);
    } else if (strcmp(ttsState, "sentence_start") == 0) {
      const char* t = doc["text"];
      speakLine[0] = 0;
      if (t) {
        strncpy(speakLine, t, sizeof(speakLine) - 1);
        speakLine[sizeof(speakLine) - 1] = 0;
      }
      renderOled();
    } else if (strcmp(ttsState, "stop") == 0) {
      playDraining = true;
      if (!i2sOn && playCount() > 0) {
        ensureI2s();
      }
      pumpPlay();
    }
#endif
  }
}

static void wsEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      wsReady = false;
      stopI2s();
      gState = ST_WIFI;
      renderOled();
      break;
    case WStype_CONNECTED:
      wsReady = true;
      sendHello();
      break;
    case WStype_TEXT: {
      if (length >= sizeof(rxbuf)) length = sizeof(rxbuf) - 1;
      memcpy(rxbuf, payload, length);
      rxbuf[length] = 0;
      onJson(rxbuf);
      break;
    }
    case WStype_BIN:
#if KATBOT_HAVE_SPEAKER
      if (gState == ST_SPEAKING || i2sOn || playDraining) {
        playPush(payload, length);
        pumpPlay();
      }
#endif
      break;
    default:
      break;
  }
}

void setup() {
  system_update_cpu_freq(160);  // INMP441 I2S requires 160 MHz for stable capture
  pinMode(PIN_LISTEN_BTN, INPUT_PULLUP);
  btnPrev = digitalRead(PIN_LISTEN_BTN);
  randomSeed(ESP.getCycleCount());
  catUiBegin();

  Wire.begin();
  oledOk = oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (oledOk) {
    oled.clearDisplay();
    oled.display();
  }

  pinMode(PIN_DHT, INPUT);  // GPIO16 requires an external DATA-to-3V3 pull-up.
  gState = ST_WIFI;
  renderOled();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint8_t tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(250);
    tries++;
    renderOled();
    yield();
  }

#if KATBOT_HAVE_SPEAKER
  playBootJingle();
#endif
  gState = ST_WIFI;
  renderOled();

  webSocket.begin(WS_HOST, WS_PORT, WS_PATH);
  webSocket.onEvent(wsEvent);
  webSocket.setReconnectInterval(3000);
  webSocket.enableHeartbeat(15000, 3000, 2);
}

void loop() {
  webSocket.loop();
  pumpPlay();

  uint32_t now = millis();
#if KATBOT_HAVE_SPEAKER
  uint16_t oledEvery = (gState == ST_SPEAKING || i2sOn) ? 360 : 120;
#else
  uint16_t oledEvery = 120;
#endif
  if (now - lastOledMs >= oledEvery) {
    renderOled();
  }

#if KATBOT_HAVE_SPEAKER
  if (gState == ST_SPEAKING || i2sOn) {
    yield();
    return;
  }
#endif

  handleButton();
  now = millis();  // startListen() may block in playMeo(); refresh before listen timeout
  sampleMic();

  if (gState == ST_LISTENING) {
    uint32_t elapsed = now - listenStartMs;
    if (now - lastMicDbgMs >= 1000) {
      lastMicDbgMs = now;
      char line[96];
      snprintf_P(
          line,
          sizeof(line),
          PSTR("mic %lums n=%lu peak=%d chunks=%lu empty=%lu rxq=%u buf=%u"),
          (unsigned long)elapsed,
          (unsigned long)micSamples,
          (int)micPeak,
          (unsigned long)micChunks,
          (unsigned long)micEmpty,
          (unsigned)i2s_rx_available(),
          (unsigned)micCount);
      sendLogLv("debug", line);
    }
    if (elapsed >= listenWindowMs) {
      finishListen();
    }
  }

  maybeDht();
  yield();
}
