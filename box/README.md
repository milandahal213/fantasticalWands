# Box — card-identified LEGO controller with a 5×5 matrix (ESP32-C6 / MicroPython)

The **box** does everything the [puck](../puck) does — it's a BLE central with a
**passive NFC card** carrying a color + serial (e.g. RED #1001). It has **no NFC
reader**; the LEGO devices read the card and then **advertise** that color +
serial. The box scans, connects only to devices advertising **its** color +
serial whose **type its behavior needs**, and runs a **hardcoded behavior**. If a
required device drops, it goes back to scanning.

On top of the puck, the box adds:

| Extra hardware | Use |
|----------------|-----|
| **5×5 NeoPixel matrix** | status display + battery gauge (replaces the puck's 3-pixel strip) |
| **Piezo buzzer** | local feedback beeps (boot, connect, run, low battery) |
| **Push button (GPIO0)** | function TBD — wired with a hook (`on_button_press`) |
| **LIS2DW12 accelerometer** | on the shared I²C bus; initialized and available (not yet used by a behavior) |

Built on this repo's raw-`bluetooth` driver (`bledevice.py`) — **no `aioble`**.

---

## Hardware

| Part | Connection |
|------|-----------|
| Board | ESP32-C6, MicroPython |
| 5×5 matrix | **25 NeoPixels on GPIO20** (row-major: 0–4 top … 20–24 bottom) |
| Buzzer | **GPIO19** (PWM piezo) |
| Button | **GPIO0** (active-low, internal pull-up) — also a wake source |
| MAX17048 fuel gauge | I²C — **SDA 22 / SCL 23**, `0x36` |
| LIS2DW12 accelerometer | same I²C bus, `0x19`; **INT1 → GPIO1** for wake-on-motion |
| NFC card | passive sticker — no wiring; carries color + serial |

Pins are constants at the top of `main.py` — adjust to your wiring. The XIAO's
external antenna is selected automatically by `bledevice.py` (GPIO3/GPIO14).

---

## Flashing & setup

1. Flash **MicroPython for ESP32-C6** (with BLE — the standard port has it).
2. Copy all `box/` files to the board (the whole `behaviors/` folder too):
   ```bash
   mpremote connect <port> fs cp config.py main.py lego_ble.py matrix.py \
       buzzer.py max17048.py lis2dw12.py program_cards.py bledevice.py \
       ble_central.py : + fs cp -r behaviors :
   ```
3. Reset the board. `main.py` runs automatically.

---

## Configure a box — just `config.py`

Identical to the puck: the only file you edit.

```python
PUCK_COLOR  = "red"          # color written on this box's card
PUCK_SERIAL = 1001           # serial written on this box's card
BEHAVIOR    = "tank_drive"   # any key in behaviors/__init__.py BEHAVIORS
```

All 14 behaviors from the puck are included unchanged (`tank_drive`,
`gyro_drive`, `line_follower`, `color_gearbox`, `radar`, `gesture_drum`, …). See
[`../puck/README.md`](../puck/README.md) for the full table and how to add one —
the `behaviors/` folder here is the same.

---

## 5×5 matrix display

The grid splits into a **battery gauge** (bottom row) and a **status/comm area**
(the top four rows):

```
rows 0–3  (pixels 0–19)   status / communication
row 4     (pixels 20–24)  battery gauge — 1 bar per 20%, colored by level
```

| Area | Shows |
|------|-------|
| Bottom row | Battery: bars fill left-to-right, green ≥80% · yellow ≥40% · orange ≥20% · red <20% (updated every 5 s) |
| Top rows — breathing | Scanning for devices |
| Top rows — white flash | A matching device was found |
| Top-row pixels solid (1 per device) | Connection progress |
| Top rows all solid | All required devices connected — behavior running |
| Whole grid red blink | Low battery (2×) or fatal config error (continuous) |

Brightness is capped at 50/255 (`_MAX_VAL` in `matrix.py`). If your grid is wired
so the battery ends up on top, swap `BATTERY_PIXELS` / `COMM_PIXELS` in `matrix.py`.

---

## Buzzer

Local feedback (separate from the LEGO devices' own beeps): a chime at boot
(pitch depends on battery level), a blip on each device connect, a note when the
behavior starts, and a low buzz when the battery is low. Pin/tones are in
`main.py` / `buzzer.py`.

## Sleep & wake

If the box scans for `IDLE_SLEEP_MS` (default 60 s) with **nothing connected**,
it goes into light sleep to save power: the matrix goes dark and the BLE radio
powers down. It wakes — resuming exactly where it left off — on either:

- a **button press** (GPIO0), or
- **movement**, via the LIS2DW12's wake-on-motion interrupt (INT1 → GPIO1).

On wake it chirps, flashes the grid once, re-enables the radio, and resumes
scanning. It only sleeps while it has zero devices connected — once anything is
connected (or the behavior is running) it stays awake.

Tuning: `IDLE_SLEEP_MS` (how long before sleeping) and `ACCEL_WAKE_THRESH` (how
much movement wakes it — lower = more sensitive) are constants in `main.py`.
Motion wake needs the accelerometer's **INT1 pin wired to `WAKE_INT_PIN`
(GPIO1)**; without that wiring the button still wakes it.

## Button (GPIO0)

Wired and debounced; each press calls `on_button_press()` in `main.py`, which
currently just chirps (and wakes the box from sleep). **TODO:** decide what a
press should do while awake — e.g. force a rescan, cycle the behavior, or mute
the buzzer. Drop your logic into that one function.

## Accelerometer

The LIS2DW12 is initialized on the shared I²C bus and available via `_accel`
(use `_accel.read()` for x/y/z). Not yet wired into a behavior — a natural future
hook (e.g. shake-to-rescan) alongside the button.

---

## Files

```
box/
  config.py       # the only file you edit per box (color, serial, behavior)
  main.py         # scan/run/self-heal loop + matrix + battery + buzzer + button + accel
  matrix.py       # 5x5 NeoPixel display (status + battery bottom row)
  buzzer.py       # piezo buzzer helper
  lis2dw12.py     # accelerometer driver
  max17048.py     # battery fuel-gauge driver
  lego_ble.py     # LEGO RPC protocol: commands, notification + advert parsing, device model
  ble_central.py  # PuckBLE transport on top of bledevice.py
  bledevice.py    # raw-bluetooth BLE central driver (multi-slot, IRQ-driven)
  program_cards.py# color remap() so PUCK_COLOR == advertised color for matching
  behaviors/      # the 14 shared behaviors (+ util.py, __init__.py registry)
  cards/          # printable behavior cards (make_cards.py + behavior_cards.pdf)
```

---

## Troubleshooting

- **Never finds devices** — tap the LEGO device onto this box's card first so it
  advertises the box's color + serial; check `PUCK_COLOR` / `PUCK_SERIAL`.
- **Matrix blank / wrong colors** — check `MATRIX_PIN` and that it's a 25-pixel
  WS2812 grid; brightness is intentionally capped at 50.
- **No battery bar** — the MAX17048 wasn't found on I²C; the box still runs, just
  without the gauge (the bottom row stays dark).
- **Connects but device won't move** — the box sends the InfoRequest handshake
  automatically; make sure no other app/box holds that device's BLE connection.
