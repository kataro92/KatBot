#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WebSocketsClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <I2S.h>

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
static DHT dht(PIN_DHT, DHT_TYPE);
static WebSocketsClient webSocket;

static DeviceState gState = ST_BOOT;
static bool oledOk = false;
static bool wsReady = false;
static char sessionId[16] = "";
static float lastTemp = NAN;
static float lastHum = NAN;
static uint32_t lastDhtMs = 0;
static uint32_t listenStartMs = 0;
static uint32_t lastOledMs = 0;
static uint8_t btnPrev = HIGH;
static uint32_t btnChangeMs = 0;

static char txbuf[192];
static char rxbuf[384];
static char speakLine[22] = "";

static int16_t micBuf[MIC_CHUNK];
static uint16_t micCount = 0;
static uint32_t nextMicUs = 0;

static int16_t playRing[PLAY_RING];
static uint16_t playW = 0;
static uint16_t playR = 0;
static bool i2sOn = false;
static bool playDraining = false;
static bool bootSinging = false;

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
  CatMood mood = bootSinging ? CAT_SPEAK : moodFromState();
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

  if (bootSinging) {
    snprintf_P(right, sizeof(right), PSTR("hello"));
  } else if (gState == ST_LISTENING) {
    uint32_t leftSec = 0;
    uint32_t elapsed = millis() - listenStartMs;
    if (elapsed < LISTEN_MS) leftSec = (LISTEN_MS - elapsed + 999) / 1000;
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

  catDraw(oled, mood, left, right);
  oled.display();
}

static void playBootJingle() {
  struct Note {
    uint16_t hz;
    uint16_t ms;
  };
  static const Note song[] PROGMEM = {
      {659, 160}, {784, 160}, {1047, 160}, {1319, 320}, {0, 140},
      {1047, 160}, {784, 160}, {659, 320},  {0, 140},
      {1319, 160}, {1568, 160}, {2093, 420},
  };
  const uint8_t nNotes = sizeof(song) / sizeof(song[0]);
  bootSinging = true;
  renderOled();
  if (!I2S.begin(I2S_PHILIPS_MODE, PLAY_HZ, 16)) {
    bootSinging = false;
    return;
  }
  i2sOn = true;
  int16_t buf[64];
  uint32_t lastFrame = millis();
  for (uint8_t n = 0; n < nNotes; n++) {
    Note note;
    memcpy_P(&note, &song[n], sizeof(Note));
    uint32_t samples = ((uint32_t)PLAY_HZ * note.ms) / 1000UL;
    uint16_t half = 0;
    if (note.hz >= 40) {
      half = (uint16_t)(PLAY_HZ / (note.hz * 2U));
      if (half < 2) half = 2;
    }
    uint16_t phase = 0;
    int16_t amp = 7200;
    int16_t s = amp;
    uint32_t fade = PLAY_HZ / 80;
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
  i2sOn = false;
  playDraining = false;
  playW = 0;
  playR = 0;
  bootSinging = false;
}

static void sendTxt() {
  if (!wsReady) return;
  webSocket.sendTXT(txbuf);
}

static void sendHello() {
  snprintf_P(
      txbuf,
      sizeof(txbuf),
      PSTR("{\"type\":\"hello\",\"version\":1,\"transport\":\"websocket\","
           "\"audio_params\":{\"format\":\"pcm\",\"sample_rate\":8000,\"channels\":1,\"bits\":16}}"));
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
        PSTR("{\"type\":\"telemetry\",\"state\":\"%s\"}"),
        stateName(gState));
  } else {
    snprintf_P(
        txbuf,
        sizeof(txbuf),
        PSTR("{\"type\":\"telemetry\",\"temp\":%.1f,\"humidity\":%.0f,\"state\":\"%s\"}"),
        lastTemp,
        lastHum,
        stateName(gState));
  }
  sendTxt();
}

static void setState(DeviceState s) {
  if (gState == s) return;
  gState = s;
  sendTelemetry();
  renderOled();
}

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
    int32_t v = ((int32_t)s * PLAY_GAIN_NUM) / PLAY_GAIN_DEN;
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
  I2S.begin(I2S_PHILIPS_MODE, PLAY_HZ, 16);
  int16_t z[32] = {0};
  i2s_write_buffer_mono_nb(z, 32);
  i2sOn = true;
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
    uint16_t avail = (uint16_t)I2S.availableForWrite();
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

static void flushMic() {
  if (micCount > 0 && wsReady) {
    webSocket.sendBIN((uint8_t*)micBuf, micCount * 2);
    micCount = 0;
  }
}

static void sampleMic() {
  if (gState != ST_LISTENING) return;
  uint32_t now = micros();
  uint8_t n = 0;
  while ((int32_t)(now - nextMicUs) >= 0 && n < 8) {
    nextMicUs += 1000000UL / MIC_HZ;
    int raw = analogRead(A0);
    int32_t s = (raw - 512) * 64;
    if (s > 32767) s = 32767;
    if (s < -32767) s = -32767;
    micBuf[micCount++] = (int16_t)s;
    if (micCount >= MIC_CHUNK) {
      if (wsReady) webSocket.sendBIN((uint8_t*)micBuf, MIC_CHUNK * 2);
      micCount = 0;
    }
    n++;
    now = micros();
  }
}

static void startListen() {
  if (gState != ST_IDLE || !wsReady) {
    return;
  }
  stopI2s();
  listenStartMs = millis();
  micCount = 0;
  nextMicUs = micros();
  gState = ST_LISTENING;
  sendListen("start");
  sendTelemetry();
  renderOled();
}

static void finishListen() {
  flushMic();
  gState = ST_THINKING;
  sendListen("stop");
  sendTelemetry();
  renderOled();
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

static void maybeDht() {
  if (gState != ST_IDLE) return;
  uint32_t t = millis();
  if (t - lastDhtMs < DHT_PERIOD_MS && lastDhtMs != 0) return;
  lastDhtMs = t;
  float h = dht.readHumidity();
  float temp = dht.readTemperature();
  if (isnan(h) || isnan(temp)) {
    return;
  }
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
    wsReady = true;
    setState(ST_IDLE);
    sendTelemetry();
  } else if (strcmp(type, "state") == 0) {
    const char* value = doc["value"];
    if (value && strcmp(value, "idle") == 0) {
      stopI2s();
      speakLine[0] = 0;
      setState(ST_IDLE);
    }
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
      if (gState == ST_SPEAKING || i2sOn || playDraining) {
        playPush(payload, length);
        pumpPlay();
      }
      break;
    default:
      break;
  }
}

void setup() {
  pinMode(PIN_LISTEN_BTN, INPUT_PULLUP);
  btnPrev = digitalRead(PIN_LISTEN_BTN);
  randomSeed(ESP.getCycleCount() ^ (uint32_t)analogRead(A0));
  catUiBegin();

  Wire.begin();
  oledOk = oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (oledOk) {
    oled.clearDisplay();
    oled.display();
  }

  dht.begin();
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

  playBootJingle();
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
  uint16_t oledEvery = (gState == ST_SPEAKING || i2sOn) ? 360 : 120;
  if (now - lastOledMs >= oledEvery) {
    renderOled();
  }

  if (gState == ST_SPEAKING || i2sOn) {
    yield();
    return;
  }

  handleButton();
  sampleMic();

  if (gState == ST_LISTENING) {
    if (millis() - listenStartMs >= LISTEN_MS) {
      finishListen();
    }
  }

  maybeDht();
  yield();
}
