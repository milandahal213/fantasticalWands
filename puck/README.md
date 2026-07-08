# Puck — card-identified LEGO controller (ESP32-C6 / MicroPython)

A **puck** is a Seeed XIAO ESP32-C6 with 3 NeoPixels and a **passive NFC card**
stuck to it carrying a color + serial (e.g. RED #1001). The puck has **no NFC
reader** — the LEGO devices do. When you tap a LEGO device onto the puck's card,
that device starts **advertising** the puck's color + serial over BLE.

The puck is a pure **BLE central**. It continuously scans and connects only to
devices that (1) advertise **its** color + serial and (2) are a **type its
behavior needs** (e.g. Tank Drive needs a Controller + a Double Motor). Once the
required devices are connected it runs the behavior; if one drops, it goes back
to scanning. It shows its color on the NeoPixels (dim while scanning, bright
while running).

Because the puck can't read its own card, its identity + behavior are
**hardcoded** in `main.py`. Built on this repo's raw-`bluetooth` driver
(`bledevice.py`) — **no `aioble` required**.

---

## Hardware

| Part | Connection |
|------|-----------|
| Board | Seeed **XIAO ESP32-C6**, MicroPython |
| NeoPixels | **3 pixels on GPIO20** |
| MAX17048 fuel gauge | I²C — **SDA = GPIO22, SCL = GPIO23**, address `0x36` (optional) |
| NFC card | passive sticker on the puck — no wiring; just carries color + serial |

(No NFC reader. The XIAO's external antenna is selected automatically by
`bledevice.py` on GPIO3/GPIO14. If no fuel gauge is present the puck just skips
battery monitoring.)

---

## Flashing & setup

1. Flash **MicroPython for ESP32-C6** (a build with BLE — the standard esp32-c6
   port includes it). No extra libraries needed — the BLE driver
   (`bledevice.py`) uses the built-in `bluetooth` module.
2. Copy all `puck/` files to the board (the whole `behaviors/` folder too):
   ```bash
   mpremote connect <port> fs cp config.py main.py lego_ble.py status.py \
       max17048.py program_cards.py bledevice.py ble_central.py : + \
       fs cp -r behaviors :
   ```
3. Reset the board. `main.py` runs automatically.

---

## Configure a puck — just `config.py`

Every puck runs identical code; the **only** file you change is `config.py`:

```python
PUCK_COLOR  = "red"          # color written on this puck's card
PUCK_SERIAL = 1001           # serial written on this puck's card
BEHAVIOR    = "tank_drive"   # any key in behaviors/__init__.py BEHAVIORS
```

`PUCK_COLOR` + `PUCK_SERIAL` decide *which* devices this puck connects to (only
those advertising the same color + serial — the ones you tapped onto its card).
`BEHAVIOR` decides *what* it does with them; its `REQUIRED` list decides *which
types* to look for. Colors: `magenta`/`pink`, `purple`, `blue`, `azure`, `teal`,
`green`, `yellow`, `orange`, `red`, `white`.

Bulk workflow: flash all pucks once, then just edit `config.py` on each.

Built-in behaviors and the devices they need:

| Key | Behavior | Requires |
|-----|----------|----------|
| `tank_drive` | Left/right sticks drive left/right motors | Controller + Double Motor |
| `arcade_drive` | Throttle + steering mix | Controller + Double Motor |
| `gyro_drive` | Drives straight using IMU heading hold | Controller + Double Motor |
| `precision_turn` | Flick stick → exact spin-in-place turn + beep | Controller + Double Motor |
| `tilt_steer` | Throttle on stick, steer by tilting (IMU roll) | Controller + Double Motor |
| `line_follower` | Rides a line edge by reflected brightness | Color Sensor + Double Motor |
| `color_gearbox` | Tap a color to set the speed "gear", then drive | Color Sensor + Controller + Double Motor |
| `motor_knob` | Hand-turn the single motor as a dial for the drive | Single Motor + Double Motor |
| `light_theremin` | Reflected brightness → single-motor speed | Color Sensor + Single Motor |
| `spin` | Spin continuously | Single Motor |
| `color_soundboard` | Each color plays a note on the sensor | Color Sensor |
| `simon_says` | Color memory game with beep feedback | Color Sensor |
| `radar` | Sweep the sensor; beep faster as things get closer | Single Motor + Color Sensor |
| `gesture_drum` | IMU taps/shakes fire drum notes; stick shifts pitch | Double Motor + Controller |

### Adding a behavior

1. Create `behaviors/my_thing.py` with a class exposing `NAME`, `REQUIRED`, and
   `tick(devices)` (plus optional `on_start` / `on_stop`):

   ```python
   from behaviors.util import find

   class MyThing:
       NAME = "My Thing"
       REQUIRED = ["controller", "double_motor"]
       def tick(self, devices):
           ctrl = find(devices, "controller")
           motor = find(devices, "double_motor")
           if ctrl and motor:
               motor.move_tank(ctrl.left or 0, ctrl.right or 0)
       def on_stop(self, devices):
           for d in devices:
               d.stop()
   ```

2. Register it in `behaviors/__init__.py` (`from behaviors.my_thing import MyThing`
   and add `"my_thing": MyThing` to `BEHAVIORS`).
3. Set `BEHAVIOR = "my_thing"` in `config.py`.

Kinds: `"single_motor"`, `"double_motor"`, `"color_sensor"`, `"controller"`.
Device methods: `.run(speed)`, `.stop()`, `.move_tank(l, r)` (double), `.beep()`.
Telemetry attributes: `.position .speed .left .right .color .reflection .yaw` …

---

## How matching works

Tap a LEGO device onto the puck's NFC card and it advertises that card's color +
serial in its BLE manufacturer data (company `0x0397`):

```
advertisement -> [grp_hi, grp_lo, color, ser_lo, ser_hi]   (+ product id = type)
match when    -> color == PUCK_COLOR  AND  serial == PUCK_SERIAL
                 AND product-type is one the behavior REQUIRES
```

The color byte is normalized with `program_cards.remap_color()` on both sides
(the puck applies it to `PUCK_COLOR` too), so the values compare cleanly. The
product id (512–515) gives each device's type, checked against the behavior's
`REQUIRED` list.

To make a Controller and a Double Motor both belong to one puck, tap **both**
onto that puck's card so they advertise the same color + serial.

---

## NeoPixel status (3 pixels)

| Pattern | Meaning |
|---------|---------|
| Breathing, puck color | Scanning for devices |
| Quick white blip | A matching device was found |
| N pixels solid (puck color), rest breathing | N devices connected so far |
| All 3 solid, bright | All required devices connected — behavior running |
| Red blinks (2×), then resumes | **Battery below 20%** (checked every 5 s) |
| Continuous red blink | Fatal error (unknown `PUCK_COLOR` or `BEHAVIOR`) |

Brightness is capped at `_MAX_VAL` (50/255) in `status.py`; low-battery threshold
is `LOW_BATT_PCT` (20%) in `main.py`.

---

## Files

```
puck/
  config.py       # <-- the only file you edit per puck (color, serial, behavior)
  main.py         # scan/run/self-heal state machine + battery monitor
  status.py       # 3-NeoPixel status display (breathe / found / progress / running / low-batt)
  max17048.py     # battery fuel-gauge driver (optional; skipped if absent)
  lego_ble.py     # LEGO RPC protocol: commands, notification + advert parsing, device model
  ble_central.py  # PuckBLE transport (discover/connect/notify) on top of bledevice.py
  bledevice.py    # repo's raw-bluetooth BLE central driver (multi-slot, IRQ-driven)
  program_cards.py# color remap() so PUCK_COLOR == advertised color for matching
  behaviors/
    __init__.py   # registry: name -> behavior class
    util.py       # find() / clamp()
    tank_drive.py  arcade_drive.py  light_theremin.py  spin.py
```

Note: `bledevice.py` switches the XIAO C6 to its **external antenna** (GPIO3/GPIO14)
before enabling the radio — the same setup the wand uses.

---

## Troubleshooting

- **Never finds devices** — tap the LEGO device onto this puck's card first, so
  it advertises the puck's color + serial. Check `PUCK_COLOR` / `PUCK_SERIAL`
  match the card, and that `program_cards.remap_color` covers your color byte.
  The scan logs each LEGO advertisement it sees and whether it matched.
- **Puck connects but the motor doesn't move** — the LEGO device needs the
  InfoRequest handshake before it accepts commands; the puck sends it
  automatically (`[0x00]` then the notification-enable). If it still won't move,
  confirm no other app or puck already holds that device's single BLE connection.
- **Wrong NeoPixel color** — `PUCK_COLOR` sets it; check the name against
  `COLOR_BY_NAME` in `lego_ble.py`.
- **Behavior never starts** — it waits until *every* `REQUIRED` device is
  connected. Watch the serial console: it logs each connection and what's still
  missing.
