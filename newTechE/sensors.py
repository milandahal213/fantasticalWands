"""
sensors.py - library of I2C input sensors for the broadcast box.

A lookup table (SENSORS) maps an I2C address to a descriptor. identify(bus)
scans the bus and returns the recognized sensors, verifying each with an
optional whoami register read so a coincidental address match isn't trusted.

Descriptor fields:
  name           human label
  short          <=10 chars, for the OLED
  kind           'joystick' (2-axis) | 'level' (single value)
  id_reg, id_val optional whoami check (None -> match by address only)
  needs_baseline capture a resting value on detect (self-centering inputs)
  read(bus,addr) -> reading (dict for joystick, int for level) or None
  drive(reading, base) -> (left_pct, right_pct), each -100..100

To add a sensor: write its read()/drive() and add an entry to SENSORS. Set a
correct id_reg/id_val when you know the whoami, else leave them None.
"""

import time


def _clip(v):
    v = int(v)
    return -100 if v < -100 else 100 if v > 100 else v


# ─── SparkFun Qwiic Joystick (addr 0x20, whoami reg 0x00 == 0x27) ──────────
_SF_JOY_SPAN = 512          # deflection from center = full speed (tune)


def _sf_joy_read(bus, addr):
    try:
        d = bus.readfrom_mem(addr, 0x03, 4)   # X msb,lsb ; Y msb,lsb
        return {"x": (d[0] << 8) | d[1], "y": (d[2] << 8) | d[3]}
    except Exception:
        return None


def _sf_joy_drive(r, base):
    if not r or not base:
        return 0, 0
    px = _clip((r["x"] - base["x"]) * 100 // _SF_JOY_SPAN)   # steer
    py = _clip((r["y"] - base["y"]) * 100 // _SF_JOY_SPAN)   # throttle
    return _clip(py + px), _clip(py - px)                    # arcade -> (left, right)


# ─── lookup table ──────────────────────────────────────────────────────────
SENSORS = {
    0x20: {
        "name": "SparkFun Qwiic Joystick", "short": "Joystick", "kind": "joystick",
        "id_reg": 0x00, "id_val": 0x27, "needs_baseline": True,
        "read": _sf_joy_read, "drive": _sf_joy_drive,
    },
    # ── add more sensors below. Template (fill read/drive, verify whoami): ──
    # 0x6F: {
    #     "name": "SparkFun Qwiic Button", "short": "Button", "kind": "level",
    #     "id_reg": 0x00, "id_val": 0x5D, "needs_baseline": False,
    #     "read": _btn_read,       # -> 0/1
    #     "drive": lambda r, base: (100, 100) if r else (0, 0),
    # },
    # 0x29: {
    #     "name": "VL53L0X distance", "short": "Distance", "kind": "level",
    #     "id_reg": 0xC0, "id_val": 0xEE, "needs_baseline": False,
    #     "read": _vl53_read,      # -> mm
    #     "drive": lambda r, base: (_map_speed(r), _map_speed(r)),
    # },
}

# Displays / non-input devices to ignore when picking an input sensor.
IGNORE_ADDRS = (0x3C, 0x3D, 0x28)   # OLED (0x3C/0x3D), WS1850S NFC (0x28)


def scan_addrs(bus):
    """All I2C addresses on the bus (for debugging what's plugged in)."""
    try:
        return sorted(bus.scan())
    except Exception:
        return []


def identify(bus, addrs=None):
    """Return [(addr, descriptor), ...] for known input sensors on `bus`.

    Match is by ADDRESS (the table says how to read it) - the OLED and NFC are
    ignored. id_reg/id_val in a descriptor are informational only; we don't gate
    on the whoami, so a slightly different firmware still works.

    Pass `addrs` (a prior scan_addrs() result) to avoid re-scanning the bus - a
    second scan on an unpopulated SoftI2C bus is slow."""
    if addrs is None:
        addrs = scan_addrs(bus)
    out = []
    for a in addrs:
        if a in IGNORE_ADDRS:
            continue
        desc = SENSORS.get(a)
        if desc:
            out.append((a, desc))
    return out


def baseline(bus, addr, desc, n=8):
    """Average a few reads to capture a resting value (needs_baseline sensors)."""
    r0 = desc["read"](bus, addr)
    if not isinstance(r0, dict):
        return None
    acc = {k: 0 for k in r0}
    cnt = 0
    for _ in range(n):
        r = desc["read"](bus, addr)
        if isinstance(r, dict):
            for k in acc:
                acc[k] += r.get(k, 0)
            cnt += 1
        time.sleep_ms(3)
    return {k: acc[k] // cnt for k in acc} if cnt else None
