# LEGO Wand Tangible Programming System — Knowledge Base

## Overview

A tangible, card-based programming system running on an ESP32-C6 wand. Users physically tap NFC cards to assemble programs that control LEGO Powered Up devices over BLE. Programs are reactive (event-driven): each rule is a trigger + up to 4 actions.

**Key concepts:**
- **Pairing card** — identifies which LEGO devices to connect (color + serial)
- **Programming card** — an NFC card encoding one opcode (event or action)
- **Rule** — `{event: opcode, body: [opcode, ...]}` — when event fires, run body
- **Deck** — the list of rules currently assembled (max 4 rules, max 4 actions each)

---

## Hardware

| Component | Chip | I²C Addr | Notes |
|-----------|------|----------|-------|
| NFC reader | PN532 | 0x24 | Reads both NTAG and MIFARE Classic cards |
| Accelerometer | LIS2DW12 | 0x19 | Used for shake detection |
| Battery gauge | MAX17048 | 0x36 | LiPo voltage + state-of-charge |
| Light sensor | OPT3002 | 0x44 | Ambient light |
| NeoPixel grid | — | GPIO 20 | 5×5 = 25 pixels |
| Button | — | GPIO 0 | Active-low, internal pull-up |
| Buzzer | — | GPIO 19 | PWM |
| Vibration motor | — | GPIO 21 | Digital out |
| I²C bus | — | SDA=22, SCL=23 | 100 kHz (SoftI2C) |
| Antenna switch A | — | GPIO 3 | LOW = external antenna path enabled |
| Antenna switch B | — | GPIO 14 | HIGH = external antenna selected |

---

## File Structure

```
lib/
  wand.py            — Low-level hardware driver (NFC, NeoPixel, button, buzzer)
  wand_ui.py         — LED display logic (layout, colors, animations)
  bledevice.py       — BLE central driver (multi-slot connection manager)
  newhub.py          — LEGO wireless protocol layer (motor commands, telemetry)
  program_cards.py   — Opcode table + NFC card read/write
  program_runtime.py — Event loop executor + action handlers
  runloop.py         — Top-level state machine
  cardpair.py        — BLE pairing flow
  lis2dw12.py        — Accelerometer driver
  max17048.py        — Battery gauge driver

tools/
  write_card.py      — Interactive tool to write opcodes to NFC cards
  key_probe.py       — Tests MIFARE auth keys on unknown cards
  shake_probe3.py    — Diagnostic for shake detection tuning
  controller_probe.py — Diagnostic for controller joystick values

Examples/
  (Various standalone examples for individual devices)
```

---

## State Machine

States managed in `runloop.py`:

```
PAIRING_IDLE  ──(tap pairing card)──▶  PAIRED_IDLE
                                             │
                                    (tap event card)
                                             ▼
                                       PROGRAMMING
                                             │
                                      (tap GO card)
                                             ▼
                                         RUNNING
                                             │
                             (tap STOP/pairing card)
                                             │
                                             ▼
                                       PROGRAMMING  (program preserved)
```

- In **PAIRING_IDLE**: only pairing cards and BATTERY card work
- In **PAIRED_IDLE/PROGRAMMING**: programming cards build the deck
- In **RUNNING**: the event loop is active; STOP and BATTERY cards work
- **BATTERY card** bypasses the pairing gate — works at any state

---

## NFC Card Types

### Pairing Cards (serial < 9000)
- **Card type**: NTAG-21x (SAK = 0x00)
- Read without authentication
- Block 5 bytes: `[0x00, color_byte, serial_hi, serial_lo, ...]`
- Color byte is remapped via `_RAW_TO_APP_COLOR` table
- Serial encodes the LEGO Connection Card number (0–9999)
- Used to identify which LEGO devices to connect (match by color + serial)

### Programming Cards (serial 9000+)
- **Card type**: MIFARE Classic 1K (SAK = 0x08/0x18) or NTAG (SAK = 0x00)
- Block 5 stores `[0x00, 0x00, serial_hi, serial_lo]` (big-endian serial)
- MIFARE Classic requires authentication before read/write

### Writing Cards
Tool: `tools/write_card.py`

Supports both card types:
- **MIFARE Classic**: tries 5 common keys (Key A and Key B each), 16-byte block write
- **NTAG/Ultralight**: no auth needed, 4-byte page write

Common keys tried in order:
```
FF FF FF FF FF FF  (default factory)
D3 F7 D3 F7 D3 F7  (NDEF)
A0 A1 A2 A3 A4 A5  (MAD)
B0 B1 B2 B3 B4 B5  (alt transport)
00 00 00 00 00 00  (all zeros)
```

---

## Complete Opcode Table

### META cards (9000–9019)

| Serial | Name | Behavior |
|--------|------|----------|
| 9000 | GO | Starts the event loop |
| 9001 | ERASE | Clears the program deck (red wipe animation) |
| 9002 | PROGRAM_MODE | Returns to programming view, refreshes LED deck |
| 9003 | STOP | Halts execution, preserves program, restores deck display |
| 9004 | BATTERY | Shows battery level on all 25 LEDs for 3 seconds |

### EVENT cards (9100–9199) — Trigger cards (yellow LED in row)

| Serial | Name | Device Required |
|--------|------|-----------------|
| 9100 | when button pressed | — (wand button) |
| 9101 | when wand shaken | — (wand accelerometer) |
| 9111 | when RED detected | Color Sensor |
| 9112 | when GREEN detected | Color Sensor |
| 9113 | when BLUE detected | Color Sensor |
| 9114 | when YELLOW detected | Color Sensor |
| 9120 | when left joystick = +1 | Controller |
| 9121 | when left joystick = -1 | Controller |
| 9122 | when right joystick = +1 | Controller |
| 9123 | when right joystick = -1 | Controller |

### MOTION: Double Motor (9400–9499) — Action cards (dark green LED)

| Serial | Name | Behavior |
|--------|------|----------|
| 9400 | move forward 1 step | Blocking: drives forward 1 rotation |
| 9401 | move backward 1 step | Blocking: drives backward 1 rotation |
| 9410 | keep moving forward | Fire-and-forget continuous drive |
| 9411 | keep moving backward | Fire-and-forget continuous drive |
| 9420 | both motors stop | Stops double motor immediately |
| 9430 | turn left 90° | Timed differential turn CCW |
| 9431 | turn right 90° | Timed differential turn CW |

### MOTION: Single Motor (9500–9599) — Action cards (light green LED)

| Serial | Name | Behavior |
|--------|------|----------|
| 9500 | single motor 1 rotation CW | Blocking: 1 full rotation clockwise |
| 9501 | single motor 1 rotation CCW | Blocking: 1 full rotation counter-clockwise |
| 9510 | run single motor CW | Fire-and-forget continuous CW |
| 9511 | run single motor CCW | Fire-and-forget continuous CCW |
| 9520 | stop single motor | Stops single motor immediately |

> **Note**: Serials 9500/9501 were originally "90° CW/CCW" but have been changed to "1 full rotation CW/CCW".

---

## Motor Control

### LEGO Product IDs
```python
SINGLE_MOTOR = 512
DOUBLE_MOTOR = 513
COLOR_SENSOR = 514
CONTROLLER   = 515
```

### Double Motor Port Convention
```python
MOTOR_LEFT  = 1   # left wheel
MOTOR_RIGHT = 2   # right wheel
MOTOR_BOTH  = 3   # both simultaneously
```

### Tank Drive Sign Convention (IMPORTANT)
The left motor is physically mounted in reverse, so signs are counter-intuitive:

| Motion | Left speed | Right speed |
|--------|-----------|-------------|
| Forward | -50 | +50 |
| Backward | +50 | -50 |
| Turn right (CW) | -50 | -50 |
| Turn left (CCW) | +50 | +50 |

### Motor Command Sequence
Motors must be **armed** before `motor_speed` updates work:
```python
hub.motor_speed(port, 0)
hub.motor_run(port, 0)   # arm
hub.motor_speed(port, 50)  # now it moves
```
Arming happens automatically at event loop start via `_arm_motors()`.

### Speed Cache (Deduplication)
To prevent motor stall from rapid re-sends, speed commands are deduplicated:
```python
hub.data['_last_speed_sent']  # (left, right) for double motor
                               # speed int for single motor
```
**After any bounded action (single_angle, turn) the cache is cleared to 0/`(0,0)`** so the next continuous-run trigger re-sends the command.

### Calibration Values
```python
# Single motor angle timing (op_single_angle)
DEGREES_PER_SEC_AT_50 = 78     # motor degrees per second at speed 50

# Double motor turn timing (op_turn)
MS_PER_DEGREE = 3.5             # milliseconds per robot-degree of rotation
                                 # 90° turn = 315ms at speed 50
```

---

## Event System

### How Events Fire
The event loop runs at ~25ms per iteration. Each iteration polls all rule events in order. The **first rule to fire** runs its full body; other rules are skipped that iteration.

Events use **rising-edge detection** with per-rule state dicts (`rule_states`). This prevents an event from continuously re-firing while its condition remains true.

### Event Pollers (`POLLERS` dict in `program_runtime.py`)

| op key | Function | Rising Edge Logic |
|--------|----------|-------------------|
| `check_button` | `check_button()` | Fires once on press, re-arms on release |
| `check_shake` | `check_shake()` | EMA motion score threshold |
| `check_color` | `check_color()` | Fires when color matches, re-arms when color changes |
| `check_controller` | `check_controller()` | Fires at ±3500 angle, re-arms below ±1500 |

### Controller Hysteresis (empirical values)
```python
ACTIVATE = 3500   # joystick angle threshold to fire
RELEASE  = 1500   # must return inside this to re-arm
# Raw leftAngle/rightAngle peaks around ±4500–4700 at full deflection
```

### NFC Polling Throttle
During execution, NFC reads are throttled to every 5th loop iteration (~125ms) to prevent I²C bus contention with BLE motor writes:
```python
CARD_POLL_EVERY = 5
```

---

## LED Display System

### 5×5 Grid Layout

```
Row 0  [card] [dev1] [dev2] [dev3] [dev4]     ← status row
Row 1  [trig] [act1] [act2] [act3] [act4]     ← rule 1
Row 2  [trig] [act1] [act2] [act3] [act4]     ← rule 2
Row 3  [trig] [act1] [act2] [act3] [act4]     ← rule 3
Row 4  [trig] [act1] [act2] [act3] [act4]     ← rule 4
```

Pixel indices: row N starts at pixel `N * 5`.

### Color Palette (max brightness = 10 per channel)

**Status row:**
| Pixel | Meaning | Color |
|-------|---------|-------|
| 0 | Bound card color | Matches card color (see CARD_COLORS) |
| 1–4 | Connected devices | Device-specific color (see below); blinks dim white while scanning; off when disconnected |

**Device status colors (pixels 1–4):**
| Device | Color | RGB |
|--------|-------|-----|
| Single Motor | Light green | (3, 10, 3) |
| Double Motor | Dark green | (0, 6, 0) |
| Color Sensor | Pink | (10, 3, 6) |
| Controller | Dark deep red | (8, 0, 2) |

Colors intentionally match the corresponding trigger/action colors so the top row visually telegraphs what's connected.

**Trigger pixel (first pixel of each rule row):**
| Event type | Color | RGB |
|------------|-------|-----|
| Wand (button/shake) | Yellow | (10, 10, 0) |
| Controller (joystick) | Dark deep red | (8, 0, 2) |
| Color sensor | Pink | (10, 3, 6) |

**Action pixels (pixels 1–4 of each rule row):**
| Action type | Color | RGB |
|-------------|-------|-----|
| Single motor | Light green | (3, 10, 3) |
| Double motor | Dark green | (0, 6, 0) |
| Empty slot | Off | (0, 0, 0) |

**Card color pixel (pixel 0):**
| Color ID | Name | RGB |
|----------|------|-----|
| 1 | MAGENTA | (10, 2, 6) |
| 2 | PURPLE | (3, 0, 10) |
| 3 | BLUE | (0, 1, 10) |
| 4 | AZURE | (0, 5, 10) |
| 5 | TURQUOISE | (0, 10, 5) |
| 6 | GREEN | (0, 10, 0) |
| 7 | YELLOW | (10, 10, 0) |
| 8 | ORANGE | (10, 5, 0) |
| 9 | RED | (10, 0, 0) |
| 10 | WHITE | (10, 10, 10) |

### Battery Display (opcode 9004)
25 LEDs proportional to SOC, held for 3 seconds:
- ≥60%: green (0, 10, 0)
- 30–59%: yellow (10, 10, 0)
- <30%: red (10, 0, 0)

### Animations

| Method | Used when |
|--------|-----------|
| `tick_idle()` | No card bound; center pixel (12) breathes white slowly |
| `tick_spinner()` | BLE scanning for devices |
| `flash_block_ack(rgb)` | Card tap accepted |
| `wipe_anim(rgb)` | ERASE card tapped (red sweep) |
| `card_tap_intro()` | Pairing card tapped (card color tint) |
| `paint_deck(program)` | Programming state; shows all rules |
| `paint_running(program, idx)` | Execution; firing rule full brightness, others at 1/4 |
| `paint_running(program, -1)` | Waiting for next event; all rules shown dim |
| `show_battery(soc)` | BATTERY card tapped |

### During Execution
- **GO tapped** → all rules shown dim immediately (`paint_running(program, -1)`)
- **Rule fires** → firing row full brightness, all others 1/4 brightness
- **Body finishes** → resets to all-dim (`paint_running(program, -1)`)
- **STOP tapped** → `paint_deck(program)` restores normal programming view

Firing rule row = **full brightness**. All other rule rows = **1/4 brightness** (each channel divided by 4). Passing `-1` as `firing_rule_idx` dims all rows.

---

## Device Connection

### BLE Slot Names
```python
'smotor'  → Single Motor
'dmotor'  → Double Motor
'color'   → Color Sensor
'ctrl'    → Controller
```

### Pairing Flow
1. User taps pairing card (NTAG, color + serial from LEGO Connection Card)
2. System scans BLE for devices advertising matching color + serial
3. Up to 4 devices can be paired per session
4. Devices stay connected until Ctrl+C or power off

### Disconnect Detection
When a device drops, its top-row LED turns off automatically. The chain:
1. `BLEDevice._irq` fires `_IRQ_PERIPHERAL_DISCONNECT` → calls registered callback via `micropython.schedule`
2. `cardpair._scan_and_connect` registers `ble.set_disconnect_callback(_on_disconnect)` on first pairing
3. Callback calls `ui.mark_disconnected(slot_name)` → looks up `slot_name → slot_index` from internal map → clears that pixel immediately

`WandUI` stores `_slot_name_to_idx` dict populated at `mark_connected(slot_idx, product_id, slot_name)` time.

### Advertised LEGO Product IDs
```
0x0200 (512) = Single Motor
0x0201 (513) = Double Motor
0x0202 (514) = Color Sensor
0x0203 (515) = Controller
```

---

## Programming System Rules

### Rule Structure
```python
rule = {
    'event': opcode_dict,    # one EVENT card
    'body':  [opcode_dict, ...],  # up to 4 action cards
}
```

### Constraints
- Max 4 rules per deck
- Max 4 actions per rule
- Only one rule fires per event-loop iteration (first match wins)
- A rule's event card can be replaced by tapping the same event again
- Duplicate event cards replace (not append) the existing rule

### Device Guard
Before any device-specific card is accepted, the system checks if the required device is connected. If not:
- Plays descending "uh oh" beep (600Hz → 400Hz)
- Short vibration
- Card is not added to the deck

| op | Required device |
|----|----------------|
| `keep_moving`, `stop_double`, `turn`, `move` | Double Motor |
| `run_single`, `stop_single`, `single_angle` | Single Motor |
| `check_color` | Color Sensor |
| `check_controller` | Controller |

---

## Adding New Opcodes

1. Choose a serial number in the appropriate range (see namespace at top of `program_cards.py`)
2. Add entry to `OPCODES` dict in `program_cards.py`:
```python
9502: {'name': 'single motor 180° CW', 'category': CAT_MOTION,
       'op': 'single_angle', 'args': {'degrees': 180, 'dir': DIR_CW}},
```
3. If it's a new `op` string, add a handler function in `program_runtime.py` and register it in `OP_HANDLERS`
4. If it requires a specific device, add the mapping to `_OP_REQUIRES` in `runloop.py`
5. Write the serial onto a blank NFC card with `tools/write_card.py`

### Serial Namespace
```
9000–9019   META    (GO, STOP, ERASE, PROGRAM_MODE, BATTERY, ...)
9100–9199   EVENT   (triggers)
9300–9399   CONTROL (reserved)
9400–9499   MOTION: double motor
9500–9599   MOTION: single motor
9600–9699   MOTION: run (reserved)
```

---

## Known Quirks & Gotchas

### External antenna must be configured before BLE activation
GPIO3 and GPIO14 are the RF antenna switch. If not configured before `ble.active(True)`, the radio defaults to the internal PCB trace antenna. Since all wands use external u.FL antennas, failing to set these pins means poor BLE range. The config is in `BLEDevice.__init__` and runs automatically — but if you ever re-instantiate BLEDevice or write custom BLE code, always set the pins first:
```python
Pin(3, Pin.OUT).value(0)
time.sleep_ms(100)
Pin(14, Pin.OUT).value(1)
# now safe to call ble.active(True)
```

### `ctx.stop` is a list, not a bool
```python
# WRONG — always True (non-empty list is truthy)
if ctx.stop: return

# CORRECT
if ctx.stop[0]: return
```

### MIFARE Classic re-selection before auth
After a failed auth attempt, the card enters halt state. You must call `InListPassiveTarget` again (re-select) before retrying auth, or subsequent auth always fails.

### `motor_angle` is unreliable
The LEGO protocol's `motor_angle` command significantly under-delivers (e.g. asked 360°, gets ~288°). **Always use timed `motor_speed` instead** for bounded motion.

### Rapid motor_speed calls cause stall
Sending `motor_speed` in a tight loop causes the LEGO firmware to stall the motor (0° motion). This is why the speed deduplication cache exists — only send if the speed actually changed.

### NFC polling starves BLE if done every loop
The PN532 `InListPassiveTarget` call is synchronous and holds I²C for 20–50ms. Calling it every 25ms loop iteration blocks BLE service, causing motor commands to become clicks. Solution: poll NFC every 5 iterations (`CARD_POLL_EVERY = 5`).

### NTAG vs MIFARE identification
Use SAK (SEL_RES byte from `InListPassiveTarget` response):
- `SAK = 0x00` → NTAG/Ultralight (no auth needed, 4-byte page writes)
- `SAK = 0x08` or `0x18` → MIFARE Classic (needs auth, 16-byte block writes)

Cards with 7-byte UIDs (starting 04...) that fail auth are almost certainly NTAG, not locked MIFARE.

### Double motor telemetry key names
```python
hub.data['position1']   # left motor encoder position
hub.data['position2']   # right motor encoder position
hub.data['yaw']         # IMU yaw in decidegrees (×10) — range ±1800
hub.data['pitch']       # IMU pitch in decidegrees
hub.data['roll']        # IMU roll in decidegrees
```

### Single motor telemetry
```python
hub.data['position1']   # encoder position (absolute)
hub.data['absolutePos1'] # absolute position
hub.data['speed1']      # current speed
```

---

## BLE Architecture

### External Antenna Configuration
The ESP32-C6 has a single 2.4GHz radio shared by WiFi, BLE, and Zigbee. GPIO3 and GPIO14 control an RF switch that routes the radio to either the onboard PCB trace antenna or a u.FL external antenna connector. **All wands have external antennas attached to the u.FL connector.**

The antenna switch is configured in `BLEDevice.__init__` **before** `ble.active(True)` — it must be set before the radio starts or the PCB antenna is used by default:

```python
Pin(3,  Pin.OUT).value(0)   # disable internal antenna path
time.sleep_ms(100)           # let RF switch settle (important!)
Pin(14, Pin.OUT).value(1)   # enable external antenna path
# then: self.ble.active(True)
```

The 100ms delay is required for the RF switch to physically settle before the radio comes up.

### Multi-Slot Connection Manager
`BLEDevice` manages multiple simultaneous connections via named slots. Each slot is independent:
```python
ble = BLEDevice()
hub = Hub(ble_device=ble, slot='dmotor')
hub.connect(product_id=DOUBLE_MOTOR, card_color=6, card_serial=26)
hub.feed(updateTime=200)   # request telemetry at 200ms intervals
```

Telemetry arrives via BLE notifications → `on_data` callback → `hub.parse()` → `hub.data` dict.

`hub.parse()` dispatches by notification type:
- Type 60: multi-sensor packet, decoded by sub-handler table
- Type 1: info/version response

---

## Diagnostics & Tools

### `tools/write_card.py`
Interactive CLI to write opcode serials to blank NFC cards. Lists all opcodes by category. Supports both MIFARE Classic and NTAG.

### `tools/key_probe.py`
Tests all 5 common MIFARE keys (Key A + Key B each = 10 attempts) on a tapped card. Reports which key works and reads block 5 content.

### `tools/shake_probe3.py`
Reads accelerometer at 50ms intervals. Shows per-axis deviation from gravity baseline and sign-flip counts in a 600ms window. Used to calibrate shake threshold.

### `tools/controller_probe.py`
Logs raw leftAngle/rightAngle values from a connected Controller. Used to determine activate/release thresholds.
