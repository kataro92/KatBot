# Hardware

ESP-12F on **NodeMCU v1.0**. No Arduino Uno.

| Part | Role |
| --- | --- |
| ESP-12F / NodeMCU v1.0 | Wi-Fi MCU |
| SSD1306 0.96" I2C (JMD0.96D-1) | OLED |
| MAX9814 | Analog mic → `A0` |
| MAX98357 + 3 W speaker | I2S amp |
| DHT11 | Temperature / humidity |
| Momentary button | Listen 5 s, active LOW |

## Wiring diagram

Follow silkscreen on each module if pin order differs (especially OLED VCC/GND).

![Wiring](https://raw.githubusercontent.com/kataro92/KatBot/main/docs/wiring.png)

## Pin map (NodeMCU labels)

| Function | Pin | GPIO | Notes |
| --- | --- | --- | --- |
| OLED SDA | D2 | 4 | I2C data |
| OLED SCL | D1 | 5 | I2C clock |
| DHT11 data | D5 | 14 | |
| Listen button | D6 | 12 | Pull-up, other side to GND |
| MAX9814 OUT | A0 | ADC | 0–3.3 V on NodeMCU |
| MAX98357 BCLK | D8 | 15 | Must be LOW at boot |
| MAX98357 LRC | D4 | 2 | WS / LRCLK |
| MAX98357 DIN | RX | 3 | Native I2S data (no Serial) |
| MAX98357 VIN | Vin | 5 V USB | For 3 W speaker |
| OLED / DHT / MAX9814 VCC | 3V3 | | |
| All GND | GND | | Common ground |

OLED JMD0.96D-1 is commonly **GND–VCC–SCL–SDA**. Speaker `+` / `−` go only to the amp, never to the ESP. Do not sample ADC while I2S is playing.

MAX9814 `GAIN` and `A/R` can stay unconnected. MAX98357 `GAIN` / `SD` can float (defaults).
