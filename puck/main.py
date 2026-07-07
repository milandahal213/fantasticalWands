"""
main.py — puck firmware entry point (Seeed XIAO ESP32-C6, MicroPython).

The puck is a BLE central with a passive NFC card stuck to it (e.g. RED #1001)
and 3 NeoPixels. It has NO NFC reader — the LEGO devices read the card and then
advertise its color + serial. The puck scans for LEGO devices advertising ITS
color + serial whose type the behavior needs, connects them, and runs the
behavior. If a required device drops, it goes back to scanning.

Per-puck settings live in config.py (identity + behavior) — the only file you
edit when bulk-flashing. Built on the repo's raw-bluetooth BLEDevice driver;
no aioble.
"""

import time
import machine

import config
import lego_ble as L
from program_cards import remap_color
from behaviors import get as get_behavior
from ble_central import PuckBLE
from status import Status
from max17048 import MAX17048

NEOPIXEL_PIN = 20
NEOPIXEL_COUNT = 3
BEHAVIOR_MS = 60
HUNT_SCAN_MS = 3000

LOW_BATT_PCT = 20        # blink red below this state-of-charge
BATT_CHECK_MS = 5000     # how often to poll the fuel gauge
BATT_I2C_SDA = 22
BATT_I2C_SCL = 23

_batt = None
_batt_last = 0


def init_battery():
    global _batt
    try:
        i2c = machine.SoftI2C(sda=machine.Pin(BATT_I2C_SDA),
                              scl=machine.Pin(BATT_I2C_SCL), freq=400_000)
        gauge = MAX17048(i2c)
        _batt = gauge if gauge.is_connected() else None
    except Exception:
        _batt = None
    print("battery gauge:", "present" if _batt else "not found")


def battery_color(soc):
    """State-of-charge -> indicator color."""
    if soc >= 80:
        return (0, 255, 0)      # green
    if soc >= 40:
        return (255, 255, 0)    # yellow
    if soc >= LOW_BATT_PCT:
        return (255, 120, 0)    # orange
    return (255, 0, 0)          # red


def battery_boot_indicator(status):
    """At boot, print the level and flash its color so people can read it."""
    if _batt is None:
        print("battery: no gauge")
        return
    try:
        soc = _batt.soc
    except Exception:
        print("battery: read failed")
        return
    print("battery: %.0f%%" % soc)
    status.blink(battery_color(soc), times=3)


def maybe_warn_battery(status):
    """Poll the fuel gauge at most every BATT_CHECK_MS; print level, blink if low."""
    global _batt_last
    if _batt is None:
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, _batt_last) < BATT_CHECK_MS:
        return
    _batt_last = now
    try:
        soc = _batt.soc
    except Exception:
        return
    print("battery: %.0f%%" % soc)
    if soc < LOW_BATT_PCT:
        status.low_battery()


def present_kinds(puck, connected):
    return [connected[s]["kind"] for s in connected if puck.is_connected(s)]


def satisfied(puck, connected, required):
    present = present_kinds(puck, connected)
    for k in required:
        if k not in present:
            return False
    return True


def still_needed(puck, connected, required):
    present = present_kinds(puck, connected)
    return [k for k in required if k not in present]


def prune(puck, connected):
    for slot in list(connected.keys()):
        if not puck.is_connected(slot):
            print("dropped:", L.KIND_LABEL.get(connected[slot]["kind"], "?"))
            puck.disconnect(slot)
            del connected[slot]


def devlist(connected):
    return [c["dev"] for c in connected.values()]


def run_puck():
    print("puck booting...")

    raw_color = L.COLOR_BY_NAME.get(str(config.PUCK_COLOR).lower())
    base_rgb = L.FW_COLOR_RGB.get(raw_color, (150, 150, 150))
    status = Status(NEOPIXEL_PIN, NEOPIXEL_COUNT, base_rgb)

    if raw_color is None:
        print("unknown PUCK_COLOR:", config.PUCK_COLOR)
        status.error()
        return

    behavior_cls = get_behavior(config.BEHAVIOR)
    if behavior_cls is None:
        print("unknown BEHAVIOR:", config.BEHAVIOR)
        status.error()
        return
    behavior = behavior_cls()

    match_color = remap_color(raw_color)     # same space as advertised color
    serial = config.PUCK_SERIAL
    print("identity:", config.PUCK_COLOR, "#%d" % serial,
          "| behavior:", behavior.NAME, "requires", behavior.REQUIRED)

    init_battery()
    battery_boot_indicator(status)
    puck = PuckBLE()
    connected = {}     # slot -> {'kind', 'addr', 'dev'}

    while True:
        # ── SCAN: connect until the behavior's required devices are present ──
        while not satisfied(puck, connected, behavior.REQUIRED):
            prune(puck, connected)
            maybe_warn_battery(status)
            status.set_progress(len(connected))
            needed = still_needed(puck, connected, behavior.REQUIRED)
            have_addrs = set(c["addr"] for c in connected.values())
            matches = puck.discover_matching(
                match_color, serial, HUNT_SCAN_MS,
                idle_cb=status.breathe_step, progress_cb=status.flash)
            for m in matches:
                if m["kind"] in needed and m["addr"] not in have_addrs:
                    print("found", L.KIND_LABEL.get(m["kind"], m["kind"]), "- connecting...")
                    slot, dev = puck.connect(m["addr_type"], m["addr"], m["kind"])
                    if dev:
                        connected[slot] = {"kind": m["kind"], "addr": m["addr"], "dev": dev}
                        print("connected:", L.KIND_LABEL.get(m["kind"], m["kind"]))
                        status.set_progress(len(connected))
                        needed = still_needed(puck, connected, behavior.REQUIRED)
                        have_addrs.add(m["addr"])

        # ── RUN: all required devices present ──
        status.running()
        print("all required devices connected - running", behavior.NAME)
        if hasattr(behavior, "on_start"):
            try:
                behavior.on_start(devlist(connected))
            except Exception as e:
                print("on_start error:", e)

        while satisfied(puck, connected, behavior.REQUIRED):
            try:
                behavior.tick(devlist(connected))
            except Exception as e:
                print("tick error:", e)
            time.sleep_ms(BEHAVIOR_MS)
            prune(puck, connected)
            maybe_warn_battery(status)

        if hasattr(behavior, "on_stop"):
            try:
                behavior.on_stop(devlist(connected))
            except Exception as e:
                print("on_stop error:", e)
        print("lost a required device - scanning again")


def main():
    try:
        run_puck()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
