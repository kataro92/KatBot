#include "cat_ui.h"

#include <Arduino.h>

enum CatAct : uint8_t {
  ACT_WALK = 0,
  ACT_PAUSE,
  ACT_SLEEP,
  ACT_PLAY,
  ACT_COUNT
};

static CatAct gAct = ACT_WALK;
static uint32_t gActUntil = 0;
static uint32_t gBlinkUntil = 0;
static uint32_t gNextBlink = 0;
static int16_t gCatX = 64;
static int8_t gDir = 1;

void catUiBegin() {
  gAct = ACT_WALK;
  gActUntil = 0;
  gBlinkUntil = 0;
  gNextBlink = 1800;
  gCatX = 64;
  gDir = 1;
}

static int8_t isin(uint8_t i) {
  static const int8_t tab[] = {0, 3, 6, 8, 9, 8, 6, 3, 0, -3, -6, -8, -9, -8, -6, -3};
  return tab[i & 15];
}

static int8_t iabs8(int8_t v) {
  return v < 0 ? (int8_t)-v : v;
}

static void pickAct(uint32_t nowMs) {
  uint8_t r = (uint8_t)random(100);
  CatAct n;
  if (r < 55) n = ACT_WALK;
  else if (r < 78) n = ACT_PAUSE;
  else if (r < 90) n = ACT_PLAY;
  else n = ACT_SLEEP;
  if (n == gAct) n = (CatAct)((n + 1) % ACT_COUNT);
  gAct = n;
  uint16_t dur = 1800 + (uint16_t)random(2500);
  if (gAct == ACT_WALK) dur = 2800 + (uint16_t)random(3500);
  if (gAct == ACT_SLEEP) dur = 3500 + (uint16_t)random(3000);
  if (gAct == ACT_PLAY) dur = 1400 + (uint16_t)random(1200);
  gActUntil = nowMs + dur;
}

void catUiTick(uint32_t nowMs, CatMood mood) {
  int8_t step = 0;
  if (mood == CAT_IDLE) {
    if (gActUntil == 0 || nowMs >= gActUntil) pickAct(nowMs);
    if (gAct == ACT_WALK) step = 2;
    else if (gAct == ACT_PLAY) step = 3;
    if (gAct != ACT_SLEEP && nowMs >= gNextBlink) {
      gBlinkUntil = nowMs + 160;
      gNextBlink = nowMs + 2200 + (uint32_t)random(1800);
    }
  } else if (mood == CAT_WIFI) {
    step = 1;
    if (nowMs > gNextBlink) gNextBlink = nowMs + 2000;
  } else if (nowMs > gNextBlink) {
    gNextBlink = nowMs + 2000;
  }
  if (step) {
    gCatX = (int16_t)(gCatX + gDir * step);
    if (gCatX < 36) {
      gCatX = 36;
      gDir = 1;
    } else if (gCatX > 108) {
      gCatX = 108;
      gDir = -1;
    }
  }
}

static void drawScenery(Adafruit_SSD1306& o, uint32_t t) {
  o.fillCircle(16, 18, 6, SSD1306_WHITE);
  o.fillCircle(19, 16, 5, SSD1306_BLACK);

  static const uint8_t stars[][2] = {
      {38, 14}, {52, 12}, {70, 16}, {88, 13}, {108, 17}, {120, 12}, {44, 22}, {96, 20}};
  uint8_t tw = (uint8_t)((t / 180) & 7);
  for (uint8_t i = 0; i < 8; i++) {
    if (((tw + i) % 5) == 0) continue;
    int16_t x = stars[i][0];
    int16_t y = stars[i][1];
    o.drawPixel(x, y, SSD1306_WHITE);
    if ((i % 3) == 0) {
      o.drawPixel(x + 1, y, SSD1306_WHITE);
      o.drawPixel(x - 1, y, SSD1306_WHITE);
      o.drawPixel(x, y + 1, SSD1306_WHITE);
      o.drawPixel(x, y - 1, SSD1306_WHITE);
    }
  }

  int16_t cx = 100 + isin((uint8_t)(t / 400)) / 3;
  o.fillCircle(cx, 20, 5, SSD1306_WHITE);
  o.fillCircle(cx + 6, 21, 4, SSD1306_WHITE);
  o.fillCircle(cx - 5, 21, 4, SSD1306_WHITE);

  o.drawCircle(28, 70, 26, SSD1306_WHITE);
  o.drawCircle(78, 74, 30, SSD1306_WHITE);
  o.drawCircle(118, 68, 22, SSD1306_WHITE);

  o.fillRect(8, 42, 3, 16, SSD1306_WHITE);
  o.fillCircle(9, 40, 7, SSD1306_WHITE);
  o.fillCircle(5, 42, 5, SSD1306_WHITE);
  o.fillCircle(14, 42, 5, SSD1306_WHITE);

  o.drawFastHLine(0, 58, 128, SSD1306_WHITE);
  for (int16_t x = 0; x < 128; x += 3) {
    uint8_t gh = (uint8_t)(1 + ((x + (int16_t)(t / 90)) % 3));
    o.drawFastVLine(x, 59, gh, SSD1306_WHITE);
  }
  o.drawPixel(22, 56, SSD1306_WHITE);
  o.drawPixel(21, 55, SSD1306_WHITE);
  o.drawPixel(23, 55, SSD1306_WHITE);
  o.drawFastVLine(22, 56, 2, SSD1306_WHITE);
  o.drawPixel(110, 56, SSD1306_WHITE);
  o.drawPixel(109, 55, SSD1306_WHITE);
  o.drawPixel(111, 55, SSD1306_WHITE);
}

static void drawChibi(Adafruit_SSD1306& o, int16_t hx, int16_t hy, int8_t facing, int8_t hop, CatMood mood, uint32_t t, bool blink) {
  int8_t tw = isin((uint8_t)(t / 70)) / 3;
  if (facing > 0) {
    o.fillCircle(hx - 10, hy + 16, 3, SSD1306_WHITE);
    o.fillCircle(hx - 14, hy + 12 + tw, 2, SSD1306_WHITE);
  } else {
    o.fillCircle(hx + 10, hy + 16, 3, SSD1306_WHITE);
    o.fillCircle(hx + 14, hy + 12 + tw, 2, SSD1306_WHITE);
  }

  o.fillCircle(hx, hy + 16, 6, SSD1306_WHITE);

  uint8_t gait = (uint8_t)((t / 80) % 4);
  bool freeze = (mood == CAT_LISTEN || mood == CAT_THINK || mood == CAT_WIFI);
  if (gAct == ACT_SLEEP && mood == CAT_IDLE) freeze = true;
  int16_t foot = 54 - hop;
  if (freeze) {
    o.fillRoundRect(hx - 4, foot, 3, 5, 1, SSD1306_WHITE);
    o.fillRoundRect(hx + 2, foot, 3, 5, 1, SSD1306_WHITE);
  } else {
    int8_t a = (gait <= 1) ? 2 : 0;
    int8_t b = (gait <= 1) ? 0 : 2;
    o.fillRoundRect(hx - 4, foot - a, 3, (int16_t)(5 + a), 1, SSD1306_WHITE);
    o.fillRoundRect(hx + 2, foot - b, 3, (int16_t)(5 + b), 1, SSD1306_WHITE);
  }

  int8_t eu = (mood == CAT_LISTEN) ? -5 : 0;
  o.fillTriangle(hx - 11, hy - 4, hx - 17, hy - 17 + eu, hx - 3, hy - 8, SSD1306_WHITE);
  o.fillTriangle(hx + 11, hy - 4, hx + 17, hy - 17 + eu, hx + 3, hy - 8, SSD1306_WHITE);
  o.fillTriangle(hx - 11, hy - 7, hx - 15, hy - 14 + eu, hx - 7, hy - 8, SSD1306_BLACK);
  o.fillTriangle(hx + 11, hy - 7, hx + 15, hy - 14 + eu, hx + 7, hy - 8, SSD1306_BLACK);

  o.fillCircle(hx, hy, 14, SSD1306_WHITE);

  int16_t ey = hy - 2;
  if (mood == CAT_THINK) ey = hy - 4;
  if (blink || (mood == CAT_IDLE && gAct == ACT_SLEEP)) {
    o.drawFastHLine(hx - 11, ey, 8, SSD1306_BLACK);
    o.drawFastHLine(hx + 3, ey, 8, SSD1306_BLACK);
  } else {
    int8_t look = (mood == CAT_LISTEN) ? 0 : (int8_t)(2 * facing);
    o.fillCircle(hx - 5, ey, 6, SSD1306_BLACK);
    o.fillCircle(hx + 5, ey, 6, SSD1306_BLACK);
    o.fillCircle(hx - 6 + look, ey - 2, 3, SSD1306_WHITE);
    o.fillCircle(hx + 4 + look, ey - 2, 3, SSD1306_WHITE);
    o.drawPixel(hx - 3 + look, ey + 1, SSD1306_WHITE);
    o.drawPixel(hx + 7 + look, ey + 1, SSD1306_WHITE);
  }

  o.drawFastHLine(hx - 11, hy + 4, 3, SSD1306_BLACK);
  o.drawFastHLine(hx + 8, hy + 4, 3, SSD1306_BLACK);
  o.drawPixel(hx, hy + 3, SSD1306_BLACK);

  if (mood == CAT_SPEAK) {
    o.fillCircle(hx, hy + 8, 3, SSD1306_BLACK);
    o.drawPixel(hx, hy + 7, SSD1306_WHITE);
  } else if (mood == CAT_IDLE && gAct == ACT_SLEEP) {
    o.drawFastHLine(hx - 3, hy + 7, 6, SSD1306_BLACK);
  } else {
    o.drawLine(hx - 5, hy + 6, hx, hy + 9, SSD1306_BLACK);
    o.drawLine(hx, hy + 9, hx + 5, hy + 6, SSD1306_BLACK);
  }

  if (mood == CAT_LISTEN) {
    uint8_t a = (uint8_t)((t / 120) % 3);
    int16_t sx = hx + (int16_t)(18 * facing);
    o.drawCircle(sx, hy - 2, (int16_t)(4 + a), SSD1306_WHITE);
    o.drawCircle(sx, hy - 2, (int16_t)(7 + a), SSD1306_WHITE);
  }
}

void catDraw(Adafruit_SSD1306& oled, CatMood mood, const char* barLeft, const char* barRight) {
  const uint32_t t = millis();
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(barLeft ? barLeft : "");
  if (barRight && barRight[0]) {
    int16_t x1, y1;
    uint16_t w, h;
    oled.getTextBounds(barRight, 0, 0, &x1, &y1, &w, &h);
    oled.setCursor((int16_t)OLED_WIDTH - (int16_t)w, 0);
    oled.print(barRight);
  }
  oled.drawFastHLine(0, OLED_BAR_H - 1, OLED_WIDTH, SSD1306_WHITE);

  drawScenery(oled, t);

  uint8_t ph = (uint8_t)(t / 80);
  int8_t hop = 0;
  int8_t facing = gDir;
  int16_t hx = gCatX;
  if (mood == CAT_SPEAK) {
    hop = (int8_t)(2 + iabs8(isin(ph)) / 3);
    facing = 1;
    hx = 64;
  } else if (mood == CAT_LISTEN) {
    hop = (int8_t)(1 + iabs8(isin((uint8_t)(ph / 2))) / 4);
    facing = 1;
    hx = 64;
  } else if (mood == CAT_THINK) {
    hop = 0;
    facing = 1;
    hx = 64;
  } else if (mood == CAT_WIFI) {
    hop = iabs8(isin(ph)) / 5;
  } else if (gAct == ACT_SLEEP) {
    hop = 0;
  } else if (gAct == ACT_PLAY) {
    hop = (int8_t)(2 + iabs8(isin(ph)) / 2);
  } else if (gAct == ACT_PAUSE) {
    hop = iabs8(isin((uint8_t)(ph / 2))) / 4;
    facing = 1;
  } else {
    hop = iabs8(isin(ph)) / 3;
  }

  bool blink = (t < gBlinkUntil) && !(mood == CAT_IDLE && gAct == ACT_SLEEP);
  int16_t hy = 34 - hop;
  drawChibi(oled, hx, hy, facing, hop, mood, t, blink);

  if (mood == CAT_IDLE && gAct == ACT_SLEEP) {
    oled.setCursor(hx + 16, 16);
    oled.print(F("z"));
    oled.setCursor(hx + 22, 10);
    oled.print(F("Z"));
  } else if (mood == CAT_THINK) {
    oled.fillCircle(hx + 18, 18, 1, SSD1306_WHITE);
    oled.fillCircle(hx + 24, 14, 1, SSD1306_WHITE);
    oled.fillCircle(hx + 30, 11, 2, SSD1306_WHITE);
  }
}
