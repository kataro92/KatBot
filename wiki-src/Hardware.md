# Hardware

ESP-12F on **NodeMCU v1.0**. No Arduino Uno.

| Part | Role |
| --- | --- |
| ESP-12F / NodeMCU v1.0 | Wi-Fi MCU |
| SSD1306 0.96" I2C (JMD0.96D-1) | OLED |
| INMP441 | I2S MEMS mic |
| MAX98357 + 3 W speaker | I2S amp |
| DHT11 | Temperature / humidity |
| Momentary button | Listen window, active LOW |

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
| INMP441 SCK + MAX98357 BCLK | D8 | 15 | Shared I2S clock, must be LOW at boot |
| INMP441 WS + MAX98357 LRC | D4 | 2 | Shared WS / LRCLK |
| INMP441 SD + MAX98357 DIN | RX | 3 | Shared I2S data (no Serial) |
| MAX98357 VIN | Vin | 5 V USB or battery boost | For 3 W speaker |
| INMP441 L/R | GND | | Left channel |
| OLED / DHT / INMP441 VCC | 3V3 | | |
| All GND | GND | | Common ground |

OLED JMD0.96D-1 is commonly **GND–VCC–SCL–SDA**. Speaker `+` / `−` go only to the amp, never to the ESP.

INMP441 shares the ESP8266 I2S bus with the MAX98357:

- `SCK` → `D8` / GPIO15
- `WS` → `D4` / GPIO2
- `SD` → `RX` / GPIO3
- `L/R` → `GND`

The ESP8266 has one I2S peripheral, so firmware switches it between **RX** (mic during `listening`) and **TX** (speaker during `speaking`). There is no full-duplex audio or barge-in. MAX98357 `GAIN` / `SD` can float (defaults).

## Battery

The board expects **5 V on `Vin`**. The NodeMCU AMS1117 then makes 3.3 V for the ESP, OLED, DHT11, and INMP441. The MAX98357 also takes 5 V from `Vin`.

Recommended: 1S 18650/LiPo → TP4056 (with protection) → 5 V boost (≥ 2 A) → **`Vin`**, GND common. Put a switch on the 5 V feed.

```text
Pin 18650 / LiPo 1S
  +  ---->  TP4056  B+
  -  ---->  TP4056  B-

TP4056 OUT+  ---->  Boost IN+
TP4056 OUT-  ---->  Boost IN-

Boost 5V OUT+  --[switch]-->  NodeMCU  Vin
Boost 5V OUT-  ------------>  NodeMCU  GND
```

- **Do** connect a regulated 5 V pack (or USB power bank) to **`Vin`** (sometimes labelled `5V` next to the barrel/header — that is the Vin rail).
- **Do not** put a 3.7 V cell on **`3V3`**. A full Li-ion is 4.2 V; ESP8266 max is about 3.6 V, and `3V3` is the regulator *output*.
- **Do not** feed a battery into USB-passthrough `VU` while a computer is also plugged in.
- Unplug USB (or open the battery switch) when flashing from a PC so the two 5 V sources do not fight.

A 5 V USB power bank into the NodeMCU USB jack is the simplest option if you do not need a built-in cell.
