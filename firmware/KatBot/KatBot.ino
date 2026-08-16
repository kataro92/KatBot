#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WebSocketsClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <ArduinoJson.h>

#include "config.h"
#include "secrets.h"

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
static char rxbuf[256];

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

static void drawCentered(int16_t y, const char* text) {
  int16_t x1, y1;
  uint16_t w, h;
  oled.getTextBounds(text, 0, y, &x1, &y1, &w, &h);
  oled.setCursor((OLED_WIDTH - (int16_t)w) / 2, y);
  oled.print(text);
}

static void renderOled() {
  if (!oledOk) return;
  lastOledMs = millis();

  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(F("Meo Bot"));

  if (gState == ST_LISTENING) {
    uint32_t left = 0;
    uint32_t elapsed = millis() - listenStartMs;
    if (elapsed < LISTEN_MS) left = (LISTEN_MS - elapsed + 999) / 1000;
    oled.setTextSize(2);
    drawCentered(22, "NGHE");
    oled.setTextSize(1);
    snprintf_P(txbuf, sizeof(txbuf), PSTR("%lus"), (unsigned long)left);
    drawCentered(48, txbuf);
  } else if (gState == ST_THINKING) {
    oled.setTextSize(2);
    drawCentered(24, "NGHI");
  } else if (gState == ST_SPEAKING) {
    oled.setTextSize(2);
    drawCentered(24, "NOI");
  } else if (gState == ST_WIFI) {
    oled.setTextSize(1);
    drawCentered(28, "WiFi...");
  } else {
    oled.setTextSize(1);
    if (!wsReady) {
      drawCentered(22, "chua ket noi");
    } else {
      drawCentered(18, "san sang");
    }
    if (!isnan(lastTemp) && !isnan(lastHum)) {
      snprintf_P(txbuf, sizeof(txbuf), PSTR("%.1fC  %.0f%%"), lastTemp, lastHum);
      drawCentered(40, txbuf);
    }
    oled.setCursor(0, 56);
    oled.print(wsReady ? F("WS ok") : F("WS --"));
  }
  oled.display();
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

static void startListen() {
  if (gState != ST_IDLE || !wsReady) {
    return;
  }
  listenStartMs = millis();
  gState = ST_LISTENING;
  sendListen("start");
  sendTelemetry();
  renderOled();
}

static void finishListen() {
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
  uint32_t t = millis();
  if (t - lastDhtMs < DHT_PERIOD_MS && lastDhtMs != 0) return;
  lastDhtMs = t;
  float h = dht.readHumidity();
  float temp = dht.readTemperature();
  if (isnan(h) || isnan(temp)) {
    Serial.println(F("DHT read fail"));
    return;
  }
  lastHum = h;
  lastTemp = temp;
  sendTelemetry();
  if (gState == ST_IDLE) renderOled();
}

static void onJson(const char* json) {
  StaticJsonDocument<512> doc;
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
    if (value && strcmp(value, "idle") == 0) setState(ST_IDLE);
  } else if (strcmp(type, "tts") == 0) {
    const char* ttsState = doc["state"];
    if (!ttsState) return;
    if (strcmp(ttsState, "start") == 0) setState(ST_SPEAKING);
    else if (strcmp(ttsState, "stop") == 0) setState(ST_IDLE);
  }
}

static void wsEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      wsReady = false;
      gState = ST_WIFI;
      Serial.println(F("WS disconnect"));
      renderOled();
      break;
    case WStype_CONNECTED:
      Serial.println(F("WS connected"));
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
    default:
      break;
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(PIN_LISTEN_BTN, INPUT_PULLUP);
  btnPrev = digitalRead(PIN_LISTEN_BTN);

  Wire.begin();
  oledOk = oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (!oledOk) {
    Serial.println(F("OLED fail"));
  } else {
    oled.clearDisplay();
    oled.display();
  }

  dht.begin();
  gState = ST_WIFI;
  renderOled();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print(F("WiFi "));
  uint8_t tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(250);
    Serial.print('.');
    tries++;
    yield();
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("IP "));
    Serial.println(WiFi.localIP());
  } else {
    Serial.println(F("WiFi fail"));
  }

  webSocket.begin(WS_HOST, WS_PORT, WS_PATH);
  webSocket.onEvent(wsEvent);
  webSocket.setReconnectInterval(3000);
  webSocket.enableHeartbeat(15000, 3000, 2);
}

void loop() {
  webSocket.loop();
  handleButton();

  if (gState == ST_LISTENING) {
    if (millis() - listenStartMs >= LISTEN_MS) {
      finishListen();
    } else if (millis() - lastOledMs >= 200) {
      renderOled();
    }
  }

  maybeDht();
  yield();
}
