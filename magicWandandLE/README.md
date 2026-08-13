# magicWandandLE — the LEGO Education "Wand" (ESP32-C6)

Firmware for a handheld wand that taps LEGO Education connection cards to
control LEGO motors. The **colour of the tapped card selects the wand's
behaviour** — no menu, no button-held mode toggle. Tap a different card at any
time to switch live.

## Hardware

ESP32-C6 board with:
- **PN532 NFC reader** (I2C, `0x24`) — reads LEGO connection cards
- **5x5 NeoPixel grid** (pin 20) — status + live sensor display
- **Button** (pin 0, active low) — the broadcast trigger (see below)
- **Buzzer** (pin 19, PWM) — jingles for card taps / scan start
- **LIS2DW12 accelerometer** (I2C, `0x19`) — tilt input for wand control
- **OPT3002 light sensor** (I2C, `0x44`)
- **MAX17048 battery gauge** (I2C, `0x36`)

I2C pins: SDA `22`, SCL `23`.

## Modes, by tapped card colour

Colours below are the **app-aligned IDs** `read_card_universal_full()` returns
(not the raw firmware byte — see `program_cards.remap_color()`). Measured on
hardware: **purple = 2, green = 6, orange = 9**. Blue is wired to `3` but is
**not yet confirmed** — see Known gaps below.

| Card | Mode | What happens |
|---|---|---|
| **Purple** (2) — and any other colour not listed below | **Wand control** | Broadcasts an FD02 type-`0x04` beacon whose speed tracks the accelerometer (tilt the wand, the motor drives). Pure connectionless broadcast — no GATT connection. |
| **Orange** (9) | **Dance** | Broadcasts random speeds/directions to a double motor (a "dance") — also pure broadcast, no connection. |
| **Green** (6), **Blue** (3, unconfirmed) | **Tap programming** | Connects (GATT) to devices wearing that exact card colour + serial, then runs the reactive tap-programming deck (tap event/action cards, GO to run). |

**Wand control** and **Dance** both:
- Only broadcast **while the button is held**. Release it and the radio stops
  advertising entirely (the motor gets no packets, not a speed-0 packet).
- Passively listen for the LEGO **colour sensor** and **controller** wearing
  the *exact same card* (colour **and** serial — a serial alone is ambiguous
  across colours) and show them on the 5x5 grid regardless of the button:
  - **Centre pixel** — the tapped card's own colour (always on, so you can
    tell which group you're in at a glance).
  - **Centre columns** (1–3, all rows) — the colour sensor's live detected
    colour.
  - **Left column** (0) / **right column** (4) — the controller's two stick
    axes as a centre-origin LED-count bar (1 LED centred, up to 3 LEDs at
    full deflection, bright green at the extreme).

Tapping a **different connection card** at any time — in any mode — switches
to whatever mode that colour maps to. A "tu-du-tu" 3-note jingle plays on every
recognized card tap; entering/re-entering tap-programming additionally plays a
longer "tu-du-tu-tu, (pause)" x4 jingle right as the scan for matching devices
begins.

## Files

| File | Role |
|---|---|
| `main.py` | Card-colour dispatch loop: reads a tap, routes to the matching mode, switches on the next different tap |
| `lib/wand.py` | `Wand` — NFC, NeoPixel grid, button, buzzer/jingles, accelerometer/light/battery accessors |
| `lib/bledevice.py` | BLE central + advertiser + passive FD02 broadcast listener (`sensor_listen`) |
| `lib/legocast.py` | `advertise_mode` (wand control) and `dance_mode`, the shared 5x5 sensor display, and the FD02 beacon builder / card hash |
| `lib/runloop.py`, `lib/cardpair.py`, `lib/program_cards.py`, `lib/program_runtime.py`, `lib/wand_ui.py` | Tap-programming: state machine, device pairing/connect, card deck lookup, event-loop execution, LED deck UI |
| `lib/newhub.py` | LEGO wireless protocol — GATT command/notification encode-decode for motors, sensors, controllers |
| `lib/lis2dw12.py`, `lib/max17048.py`, `lib/buzzer.py` | Individual sensor/peripheral drivers |
| `accel_test.py` | Standalone accelerometer readout test |
| `broadcast_probe.py` | Diagnostic: dumps raw FD02/manufacturer-data broadcasts from every LEGO device in range, printing only on change — useful for reverse-engineering byte layouts |

## The FD02 broadcast protocol

12-byte Service Data (UUID `0xFD02`):

| byte | meaning |
|---|---|
| 0 | type tag — `0x02` colour sensor, `0x03` controller, `0x04` double-motor drive |
| 1 | card colour (firmware code) |
| 2 | per-card token (half of a CRC-16 over the card's 7-byte NFC UID) |
| 3–4 | card serial, little-endian |
| 5 | **colour sensor**: live detected colour (firmware code, `0xff` = none) |
| 5 | **motor drive (`0x04`)**: RIGHT wheel speed |
| 6 | **controller**: LEFT stick — **signed low nibble**: `0`=stop, `1/2/3`=+1..+3, `D/E/F`=−1..−3, `4`–`C`=dead/out-of-range (high nibble unused) |
| 6 | **motor drive (`0x04`)**: LEFT wheel speed |
| 7 | per-card token, other half |
| 8 | `0x80` const (motor drive) / unidentified slowly-varying value (sensors) |
| 9–11 | rolling counter — must keep advancing or a receiving motor treats packets as stale |

**Group = card colour + serial.** A device only acts on / is shown for
broadcasts matching the exact card it was tapped with.

## Known gaps

- **Blue's app-colour ID (`3`) is a placeholder**, inferred from
  `remap_color()`'s passthrough rule — not measured on hardware. That same
  assumption was wrong for orange (raw `8` → app `9`, not `8`). Tap the
  physical blue card, read the `tap: color=` print, and fix `PROGRAM_COLORS`
  in `main.py` if it differs.
- **Concurrent advertise + scan** (needed so wand-control/dance can broadcast
  a beacon while simultaneously listening for the colour sensor/controller)
  is implemented but **not yet verified on the ESP32-C6 radio**. If the motor
  doesn't respond, or the sensor display stays blank, this is the first thing
  to check — the fallback is to time-slice (advertise a while, pause, scan)
  instead of running both at once.

## Flashing

Copy `main.py` to the device root and everything under `lib/` to the device's
`/lib/` (MicroPython auto-adds `/lib` to the import path, so the unqualified
`from wand import Wand`-style imports resolve as-is).
