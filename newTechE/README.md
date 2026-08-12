# newTechE — tap-a-card, drive LEGO motors over BLE broadcast

A **Raspberry Pi Pico W** box that drives **LEGO Education** motors over Bluetooth
by **connectionless broadcast** — no pairing, no GATT connection. You tap a LEGO
connection card on an NFC reader to pick which motor group to target, feed the box
a local input (analog sensors or an I²C joystick), and it broadcasts a drive beacon.
Every LEGO motor grouped to that card acts on it — **many motors at once**.

- **Firmware:** MicroPython v1.28.0 on Pico W
- **Website (`web/`):** flashes the Pico and hosts build/usage guides — desktop **Chrome/Edge** (Web Serial)

## Why broadcast (not a connection)

A connection-based design (Pico as BLE central) works for **one** motor, but the
Pico W can't run a GATT client on a second simultaneous connection. Broadcast needs
no connection and drives any number of listening motors, so that's what this uses.

## Hardware / pin map

| Pins | Use |
|---|---|
| GP0 / GP1 | NFC reader (WS1850S), I²C — tap a card to pick the motor group |
| GP4 / GP5 | I²C bus — OLED and/or an I²C input sensor (e.g. joystick) |
| GP26 / GP27 | analog (ADC0/ADC1) — two LDRs/pots = left / right wheel |
| GP28 | WS2812 NeoPixel — shows the tapped card's color |

The OLED is a 64×48-visible panel (top ~16 px off-screen): draw with
`OLED_Y_OFFSET = 16`, `LINE_PITCH = 8`, ≤ 6 lines.

> **I²C tip:** the box enables the RP2040's internal pull-ups and uses a short
> SoftI²C timeout so an **empty** GP4/5 bus doesn't float and stall the loop. For a
> rock-solid bare bus, add external 4.7 kΩ pull-ups on GP4/GP5 → 3V3.

## Files

| File | Role |
|---|---|
| `main.py` | Boots `broadcast_main.main()` on power-up |
| `broadcast_main.py` | The app loop: detect input → read it → broadcast → show status |
| `lego_broadcast.py` | `Broadcaster`: `set_card(uid, serial, color)`, `emit(left%, right%)`, `stop()`. Computes the beacon hash from the card UID |
| `sensors.py` | I²C input-sensor library (address → descriptor table). SparkFun Qwiic Joystick registered at 0x20 (arcade drive). Add a sensor = add a table entry |
| `nfc_serial.py` | Reads a LEGO card → `(uid, serial, color)` |
| `ws1850s.py` | WS1850S / MFRC522-compatible NFC reader driver |
| `ssd1306.py`, `font5x7.py` | OLED driver + 5×7 font |
| `web/` | PyScript site: Web-Serial flasher + guides. `manifest.json` lists what the Flash button writes |

## How it behaves

- **Input priority:** if a recognized I²C sensor (see `sensors.py`) is present on either
  bus, it drives and the analog pins are ignored. Otherwise the analog GP26/GP27 inputs drive.
- **Analog (GP26 → left, GP27 → right):** deflection from a startup baseline, with
  averaging + a deadzone (speed ramps up *from zero* at the deadzone edge — no jump).
- **Joystick (SparkFun Qwiic, 0x20):** arcade mix (X steer, Y throttle → L/R), self-centering.
- **NFC tap** sets the broadcast target (color + serial + UID → hash) and lights the
  NeoPixel with the card's color. Tap a different card any time to retarget mid-run.
  Polling is adaptive: **fast while the reader is empty** (a tap is caught almost
  instantly) and **slow while a card is held** (so the read doesn't stall the loop).
- The box always broadcasts **type 0x04** (double-motor drive), regardless of input mode.

## FD02 broadcast protocol

Advertise **Service Data, UUID 0xFD02**, 12-byte payload:

| byte | meaning |
|---|---|
| 0 | type tag (**0x04** = double-motor drive; 0x03 = controller; 0x02 = colour sensor) |
| 1 | card colour |
| 2 | card hash **HI** (required) |
| 3–4 | card serial (little-endian) |
| 5 | **LEFT** wheel speed |
| 6 | **RIGHT** wheel speed |
| 7 | card hash **LO** (required) |
| 8 | 0x80 constant |
| 9–11 | 24-bit rolling counter — **must keep advancing** or packets are ignored as stale |

Wrapped as `02 01 06` (flags) + `len 16 02 FD <12-byte payload>`, re-advertised ~25 Hz.

- **Card hash (byte 2 : byte 7)** = CRC-16 of the card's **7-byte NFC UID** (poly `0x0001`,
  reflected in/out, init 0). The UID is **not** in the beacon, so you must read the card by
  NFC tap to compute it (`lego_broadcast.card_hash(uid)`).
- **Group = card colour + serial.** A motor obeys only beacons matching the card tapped on
  *that* motor — so tap the same card on the motor(s) and on the box.
- **Type-0x04 speed byte:** signed-8 clamped to ±100. `0x00` stop; `0x01..0x64` forward
  (`0x64` = +100); `0x9C` = −100, through `0xFF` (−1) to stop. Dead band `0x65..0x9B` = no
  motion — `_speed8()` clamps to ±100 so it never lands there.

## Run / flash

- **Standalone:** on boot `main.py` runs the app. Tap a card, provide input.
- **Website:** serve the repo folder (`python3 -m http.server 8000`) and open
  `web/index.html` in Chrome/Edge, or host on GitHub Pages. Connect the Pico → **Flash**
  writes the files listed in `web/manifest.json`.
- A firmware (MicroPython) update **wipes the filesystem** — reflash the modules afterward.
