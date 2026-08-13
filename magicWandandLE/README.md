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

## Tap programming — cards & opcodes (GREEN / BLUE mode)

A program is a **deck of up to 4 rules**, each `{event card} → up to 4 action
cards`. Tap an EVENT card to start a new rule (re-tapping the same event
replaces that rule); tap any other programming card to append it to the
*current* rule's body. Tap **GO** to run the deck: every rule's event is
polled each loop, and when one fires (on its rising edge) its body runs start
to finish before the next event is checked.

Every programming card is an NFC tag whose **serial number** — not its
colour — selects the opcode; the catalog lives in `lib/program_cards.py`'s
`OPCODES` table, and `tools/write_card.py` writes a chosen serial onto a
blank card. Each category has its own LED colour (used for tap-acknowledgment
flashes and the deck display).

**META** (white)
| Card | Effect |
|---|---|
| GO | run the assembled deck |
| STOP | halt a running deck — the program is **kept**, not erased |
| ERASE | clear the whole deck |
| PROGRAM_MODE | return to assembling rules |
| BATTERY | show battery % — works any time, doesn't interrupt a run |

**EVENT** (yellow) — tap to start a new rule; fires once per rising edge
| Card | Fires when... | Needs |
|---|---|---|
| when button pressed | the wand's button transitions to pressed | — |
| when wand shaken | recent motion energy crosses a threshold (with hysteresis so one shake can't double-fire) | — |
| when RED / GREEN / BLUE / YELLOW detected | the colour sensor's reading first matches that colour | Color Sensor |
| when left/right joystick = +1 / −1 | that stick is pushed fully to its positive/negative extreme | Controller |

**MOTION — Double Motor** (teal)
| Card | Effect |
|---|---|
| move forward / backward 1 step | drive 1 rotation — **blocks** until done |
| keep moving forward / backward | starts continuously — returns immediately |
| both motors stop | halts both motors |
| turn left / right 90° | in-place turn — blocks until done |

**MOTION — Single Motor** (teal)
| Card | Effect |
|---|---|
| single motor 90° CW / CCW | rotate ~90° — blocks until done |
| run single motor CW / CCW | starts continuously — returns immediately |
| stop single motor | halts the single motor |

A MOTION card is rejected (error beep, ignored) if its required device
(Double Motor / Single Motor) isn't connected yet. `CAT_CONTROL` and
`CAT_SENSING` are defined categories (with reserved LED colours) that have no
cards implemented yet — everything sensing-related today is an EVENT card.

To add a new card: add an entry to `OPCODES` with an unused serial (9000+),
then write that serial onto a blank NFC card with `tools/write_card.py`.

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
| `extras/accel_test.py` | Standalone accelerometer readout test |
| `extras/broadcast_probe.py` | Diagnostic: dumps raw FD02/manufacturer-data broadcasts from every LEGO device in range, printing only on change — useful for reverse-engineering byte layouts |
| `extras/MOTOR_BROADCAST_RECIPE.md` | One-page recipe for driving a LEGO motor by broadcast from *any* device (not just this wand) — the protocol reference behind `lib/legocast.py` |
| `tools/KNOWLEDGE_BASE.md` | Design doc for the tap-programming system: pairing cards, programming cards, rules/deck, opcode model |
| `tools/write_card.py` | Utility to write a programming-card opcode's serial onto a blank NFC tag (MIFARE Classic), for making new physical action/event cards |

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

Only `main.py` and `lib/` go on the device: copy `main.py` to the device root
and everything under `lib/` to the device's `/lib/` (MicroPython auto-adds
`/lib` to the import path, so the unqualified `from wand import Wand`-style
imports resolve as-is). `extras/` and `tools/` are dev-machine-only —
diagnostics, docs, and the card-writing utility — and don't need to be on
the wand's filesystem.
