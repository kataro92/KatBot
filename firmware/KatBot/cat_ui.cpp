#include "cat_ui.h"
#include "cat_bitmaps.h"

#include <Arduino.h>

static uint32_t gBlinkUntil = 0;
static uint32_t gNextBlink = 0;
static int8_t gBob = 0;

void catUiBegin() {
  gBlinkUntil = 0;
  gNextBlink = 1800;
  gBob = 0;
}

void catUiTick(uint32_t nowMs, CatMood mood) {
  if (mood == CAT_IDLE) {
    if (nowMs >= gNextBlink) {
      gBlinkUntil = nowMs + 140;
      gNextBlink = nowMs + 2400 + (uint32_t)random(1600);
    }
    gBob = (int8_t)(((nowMs / 420) & 1));
  } else {
    gBob = 0;
    if (nowMs > gNextBlink) gNextBlink = nowMs + 2000;
  }
}

static void fillDither(Adafruit_SSD1306& o, int16_t x, int16_t y, int16_t w, int16_t h) {
  for (int16_t yy = y; yy < y + h; yy++) {
    for (int16_t xx = x + ((yy + x) & 1); xx < x + w; xx += 2) {
      o.drawPixel(xx, yy, SSD1306_WHITE);
    }
  }
}

static void drawRaised(Adafruit_SSD1306& o, int16_t x, int16_t y, int16_t w, int16_t h) {
  o.drawFastHLine(x, y, w - 1, SSD1306_WHITE);
  o.drawFastVLine(x, y, h - 1, SSD1306_WHITE);
  o.drawFastHLine(x + 1, y + h - 1, w - 1, SSD1306_WHITE);
  o.drawFastVLine(x + w - 1, y + 1, h - 1, SSD1306_WHITE);
  o.drawPixel(x + w - 1, y, SSD1306_WHITE);
  o.drawPixel(x, y + h - 1, SSD1306_WHITE);
}

static void drawSunken(Adafruit_SSD1306& o, int16_t x, int16_t y, int16_t w, int16_t h) {
  o.drawFastHLine(x, y, w, SSD1306_WHITE);
  o.drawFastVLine(x, y, h, SSD1306_WHITE);
  o.drawFastHLine(x + 1, y + 1, w - 2, SSD1306_BLACK);
  o.drawFastVLine(x + 1, y + 1, h - 2, SSD1306_BLACK);
}

static void drawCaptionBtn(Adafruit_SSD1306& o, int16_t x, int16_t y, uint8_t kind) {
  o.fillRect(x, y, 9, 9, SSD1306_WHITE);
  o.drawRect(x, y, 9, 9, SSD1306_BLACK);
  o.drawFastHLine(x, y, 8, SSD1306_WHITE);
  o.drawFastVLine(x, y, 8, SSD1306_WHITE);
  if (kind == 0) {
    o.drawFastHLine(x + 2, y + 6, 5, SSD1306_BLACK);
  } else if (kind == 1) {
    o.drawRect(x + 2, y + 2, 5, 5, SSD1306_BLACK);
  } else {
    o.drawLine(x + 2, y + 2, x + 6, y + 6, SSD1306_BLACK);
    o.drawLine(x + 6, y + 2, x + 2, y + 6, SSD1306_BLACK);
  }
}

static void drawSysMenu(Adafruit_SSD1306& o, int16_t x, int16_t y) {
  o.fillRect(x, y, 9, 9, SSD1306_WHITE);
  o.drawRect(x, y, 9, 9, SSD1306_BLACK);
  o.drawFastHLine(x + 2, y + 3, 5, SSD1306_BLACK);
  o.drawFastHLine(x + 2, y + 5, 5, SSD1306_BLACK);
}

static const uint8_t* catBitmap(CatMood mood, uint32_t t, bool blink) {
  if (mood == CAT_LISTEN) return cat_listen;
  if (mood == CAT_THINK) return cat_think;
  if (mood == CAT_SPEAK) return cat_speak;
  if (mood == CAT_WIFI) return cat_wifi;
  if (blink) return cat_blink;
  return ((t / 420) & 1) ? cat_idle2 : cat_idle;
}

static void drawProgress(Adafruit_SSD1306& o, int16_t x, int16_t y, int16_t w, uint8_t pct) {
  drawSunken(o, x, y, w, 8);
  if (pct > 100) pct = 100;
  int16_t inner = w - 4;
  int16_t fill = (int16_t)((inner * pct) / 100);
  if (fill > 0) o.fillRect(x + 2, y + 2, fill, 4, SSD1306_WHITE);
  if (fill < inner) fillDither(o, x + 2 + fill, y + 2, inner - fill, 4);
}

void catDraw(
    Adafruit_SSD1306& oled,
    CatMood mood,
    const char* barLeft,
    const char* barRight,
    uint8_t progress) {
  const uint32_t t = millis();
  oled.clearDisplay();

  fillDither(oled, 0, 0, OLED_WIDTH, OLED_HEIGHT);
  oled.fillRect(1, 1, OLED_WIDTH - 2, OLED_HEIGHT - 2, SSD1306_BLACK);
  drawRaised(oled, 0, 0, OLED_WIDTH, OLED_HEIGHT);

  oled.fillRect(2, 2, OLED_WIDTH - 4, OLED_TITLE_H, SSD1306_WHITE);
  drawSysMenu(oled, 3, 3);
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  oled.setCursor(14, 4);
  oled.print(F("Meo Bot"));
  drawCaptionBtn(oled, 96, 3, 0);
  drawCaptionBtn(oled, 106, 3, 1);
  drawCaptionBtn(oled, 116, 3, 2);

  const int16_t cy = 2 + OLED_TITLE_H;
  const int16_t ch = OLED_HEIGHT - cy - 2;
  oled.fillRect(2, cy, OLED_WIDTH - 4, ch, SSD1306_BLACK);
  drawSunken(oled, 2, cy, OLED_WIDTH - 4, ch);

  const int16_t ix = 4;
  const int16_t iy = cy + 1;
  bool blink = (t < gBlinkUntil);
  oled.drawBitmap(ix, iy + gBob, catBitmap(mood, t, blink), CAT_BMP_W, CAT_BMP_H, SSD1306_WHITE);

  const int16_t tx = 48;
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(tx, iy + 2);
  oled.print(barRight ? barRight : "");
  oled.setCursor(tx, iy + 12);
  if (barLeft && barLeft[0]) {
    const char* p = barLeft;
    if (p[0] == '*' || p[0] == '-') {
      oled.fillRect(tx, iy + 12, 5, 5, SSD1306_WHITE);
      if (p[0] == '*') oled.fillRect(tx + 1, iy + 13, 3, 3, SSD1306_BLACK);
      p += (p[1] == ' ') ? 2 : 1;
      oled.setCursor(tx + 8, iy + 12);
    }
    oled.print(p);
  }

  if (mood == CAT_LISTEN && progress <= 100) {
    drawProgress(oled, tx, iy + 22, 72, progress);
  }
}
