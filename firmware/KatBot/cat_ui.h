#pragma once

#include <Adafruit_SSD1306.h>
#include "config.h"

enum CatMood : uint8_t {
  CAT_WIFI = 0,
  CAT_IDLE,
  CAT_LISTEN,
  CAT_THINK,
  CAT_SPEAK
};

void catUiBegin();
void catUiTick(uint32_t nowMs, CatMood mood);
void catDraw(
    Adafruit_SSD1306& oled,
    CatMood mood,
    const char* barLeft,
    const char* barRight,
    uint8_t progress);
