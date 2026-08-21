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

Mic and amp use **separate** ESP8266 I2S buses: mic = `I2SI_*`, amp = `I2SO_*` (clocks not shared).

### SSD1306 0.96" I2C (`0x3C`)

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| GND | GND | — | Common ground |
| VCC | 3V3 | — | 3.3 V |
| SCL | D1 | 5 | I2C clock |
| SDA | D2 | 4 | I2C data |

JMD0.96D-1 is commonly **GND–VCC–SCL–SDA**. Follow silkscreen if VCC/GND are swapped.

### INMP441 (I2S mic) — full and mic-only

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| VDD | 3V3 | — | 3.3 V |
| GND | GND | — | Common ground |
| L/R | GND | — | Left channel |
| SD | **D6** | 12 | `I2SI_DATA` |
| SCK | **D7** | 13 | `I2SI_BCK` |
| WS | **D5** | 14 | `I2SI_WS` |

### MAX98357 + speaker — mic+loa (`v0.2.x`) only

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| VIN | Vin | — | 5 V USB or battery boost, for 3 W |
| GND | GND | — | Common ground |
| DIN | **RX** | 3 | `I2SO_DATA`; no Serial debug |
| BCLK | **D8** | 15 | `I2SO_BCK` (not shared with mic) |
| LRC | **D4** | 2 | `I2SO_WS` |
| GAIN | — | — | Leave floating (default gain) |
| SD (shutdown) | 3V3 | — | Keep amplifier enabled |
| Speaker + / − | MAX98357 + / − | — | Never wire the speaker to the ESP |

Mic-only builds: omit the amp and speaker.

### DHT11

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| VCC | 3V3 | — | 3.3 V |
| DATA | **D0** | 16 | Add a **4.7–10 kΩ pull-up resistor** from DATA to 3V3 |
| GND | GND | — | Common ground |

GPIO16 has no internal pull-up, so firmware reads DHT11 with a dedicated
GPIO16-compatible routine. A bare 4-pin sensor needs the external resistor;
some 3-pin modules already include one on the PCB.

### Listen button

| Module pin | NodeMCU | GPIO | Notes |
| --- | --- | --- | --- |
| A | **D3** | 0 | `INPUT_PULLUP`, active LOW (do not hold at boot) |
| B | GND | — | Press connects D3 to GND |

Firmware enables I2S RX while listening and TX while speaking. No full-duplex audio or barge-in.

Speaker `+` / `−` go only to the amp, never to the ESP.

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
