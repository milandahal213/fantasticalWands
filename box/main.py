"""
main.py — box firmware entry point (ESP32-C6, MicroPython).

The box does everything the puck does — it's a BLE central with a passive NFC
card (color + serial) that connects to the LEGO devices tapped onto that card
and runs a hardcoded behavior. The box's extra hardware vs the puck:

    * 5x5 NeoPixel matrix  (status + battery gauge)   -> matrix.py
    * piezo buzzer         (local feedback)           -> buzzer.py
    * push button on GPIO0 (function TBD — hook below)
    * LIS2DW12 accelerometer (shared I2C)             -> lis2dw12.py

Per-box settings live in config.py (identity + behavior). Built on the repo's
raw-bluetooth BLEDevice driver; no aioble.
"""

import time
import machine

import config
import lego_ble as L
from program_cards import remap_color
from behaviors import get as get_behavior
from ble_central import PuckBLE
from matrix import Matrix
from buzzer import Buzzer
from max17048 import MAX17048
from lis2dw12 import LIS2DW12

# ── hardware pins (adjust to your box wiring) ────────────────────────────────
MATRIX_PIN = 20          # 5x5 NeoPixel data pin
BUZZER_PIN = 19          # piezo buzzer
BUTTON_PIN = 0           # push button (active-low, internal pull-up)
WAKE_INT_PIN = 1         # LIS2DW12 INT1 wired here (wake-on-motion)
I2C_SDA = 22
I2C_SCL = 23             # MAX17048 (0x36) + LIS2DW12 (0x19) share this bus
# ─────────────────────────────────────────────────────────────────────────────

BEHAVIOR_MS = 60
HUNT_SCAN_MS = 3000
LOW_BATT_PCT = 20
BATT_CHECK_MS = 5000
IDLE_SLEEP_MS = 60000    # sleep after this long scanning with nothing connected
ACCEL_WAKE_THRESH = 8    # motion sensitivity to wake (lower = more sensitive)

_batt = None
_accel = None
_buzzer = None
_button = None
_btn_prev = 1
_batt_last = 0


# ── peripherals ──────────────────────────────────────────────────────────────

def init_peripherals():
    global _batt, _accel, _buzzer, _button
    _buzzer = Buzzer(BUZZER_PIN)
    _button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    try:
        i2c = machine.SoftI2C(sda=machine.Pin(I2C_SDA),
                              scl=machine.Pin(I2C_SCL), freq=400_000)
        gauge = MAX17048(i2c)
        _batt = gauge if gauge.is_connected() else None
        try:
            acc = LIS2DW12(i2c)
            acc.init()
            _accel = acc if acc.device_id() != 0 else None
        except Exception:
            _accel = None
    except Exception:
        _batt = None
        _accel = None
    print("battery:", "yes" if _batt else "no",
          "| accel:", "yes" if _accel else "no")


def read_battery():
    if _batt is None:
        return None
    try:
        return _batt.soc
    except Exception:
        return None


def battery_color(soc):
    if soc >= 80:
        return (0, 255, 0)
    if soc >= 40:
        return (255, 255, 0)
    if soc >= LOW_BATT_PCT:
        return (255, 120, 0)
    return (255, 0, 0)


def battery_boot_indicator(mtx):
    soc = read_battery()
    if soc is None:
        print("battery: no gauge")
        return
    print("battery: %.0f%%" % soc)
    mtx.set_battery(soc)
    mtx.blink(battery_color(soc), times=3)
    if _buzzer:
        _buzzer.beep(880 if soc >= LOW_BATT_PCT else 220, 120)


def maybe_warn_battery(mtx):
    """Poll the gauge every BATT_CHECK_MS; update the bottom row, warn if low."""
    global _batt_last
    if _batt is None:
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, _batt_last) < BATT_CHECK_MS:
        return
    _batt_last = now
    soc = read_battery()
    if soc is None:
        return
    print("battery: %.0f%%" % soc)
    mtx.set_battery(soc)
    if soc < LOW_BATT_PCT:
        if _buzzer:
            _buzzer.beep(220, 80)
        mtx.low_battery()


# ── button (function TBD) ────────────────────────────────────────────────────

def on_button_press():
    """Called on each button press. TODO: decide what the button should do
    (force a rescan, cycle behavior, mute, ...). For now it just chirps."""
    print("button pressed")
    if _buzzer:
        _buzzer.beep(660, 60)


def poll_button():
    global _btn_prev
    if _button is None:
        return
    v = _button.value()
    if v == 0 and _btn_prev == 1:      # falling edge = press (active-low)
        on_button_press()
    _btn_prev = v


def enter_sleep(mtx, puck):
    """Low-power light sleep. Wakes on a button press OR accelerometer motion,
    then resumes right here. Used when nothing has connected for a while."""
    global _btn_prev
    print("idle — going to sleep (press button or move to wake)")
    if _buzzer:
        _buzzer.beep(330, 80)
    mtx.clear()

    # arm wake sources
    try:
        _button.irq(trigger=machine.Pin.IRQ_FALLING, wake=machine.SLEEP)
    except Exception as e:
        print("button wake arm failed:", e)
    if _accel is not None:
        try:
            _accel.enable_wake_int1(threshold=ACCEL_WAKE_THRESH)
            wake_pin = machine.Pin(WAKE_INT_PIN, machine.Pin.IN)
            wake_pin.irq(trigger=machine.Pin.IRQ_RISING, wake=machine.SLEEP)
        except Exception as e:
            print("accel wake arm failed:", e)

    # power down the radio while asleep
    try:
        puck.ble.ble.active(False)
    except Exception:
        pass

    try:
        machine.lightsleep()          # blocks until a wake source fires
    except Exception as e:
        print("lightsleep unavailable, staying awake:", e)

    # ── woke up ──
    try:
        puck.ble.ble.active(True)
    except Exception:
        pass
    if _accel is not None:
        try:
            _accel.clear_wake()
        except Exception:
            pass
    _btn_prev = 1                      # avoid a phantom press right after wake
    if _buzzer:
        _buzzer.beep(880, 80)
    mtx.blink(mtx.base, times=1)
    print("woke up — scanning")


# ── behavior orchestration (same as the puck) ────────────────────────────────

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


def run_box():
    print("box booting...")

    raw_color = L.COLOR_BY_NAME.get(str(config.PUCK_COLOR).lower())
    base_rgb = L.FW_COLOR_RGB.get(raw_color, (150, 150, 150))
    mtx = Matrix(MATRIX_PIN, base_rgb)

    if raw_color is None:
        print("unknown PUCK_COLOR:", config.PUCK_COLOR)
        mtx.error()
        return

    behavior_cls = get_behavior(config.BEHAVIOR)
    if behavior_cls is None:
        print("unknown BEHAVIOR:", config.BEHAVIOR)
        mtx.error()
        return
    behavior = behavior_cls()

    match_color = remap_color(raw_color)
    serial = config.PUCK_SERIAL
    print("identity:", config.PUCK_COLOR, "#%d" % serial,
          "| behavior:", behavior.NAME, "requires", behavior.REQUIRED)

    init_peripherals()
    battery_boot_indicator(mtx)
    puck = PuckBLE()
    connected = {}     # slot -> {'kind', 'addr', 'dev'}
    idle_start = None  # when we started scanning with nothing connected

    while True:
        # ── SCAN: connect until the behavior's required devices are present ──
        while not satisfied(puck, connected, behavior.REQUIRED):
            prune(puck, connected)

            # sleep if nothing has connected for a while; wake on button/motion
            if not connected:
                if idle_start is None:
                    idle_start = time.ticks_ms()
                elif time.ticks_diff(time.ticks_ms(), idle_start) > IDLE_SLEEP_MS:
                    enter_sleep(mtx, puck)
                    idle_start = time.ticks_ms()   # restart the idle countdown
            else:
                idle_start = None

            maybe_warn_battery(mtx)
            poll_button()
            mtx.set_progress(len(connected))
            needed = still_needed(puck, connected, behavior.REQUIRED)
            have_addrs = set(c["addr"] for c in connected.values())
            matches = puck.discover_matching(
                match_color, serial, HUNT_SCAN_MS,
                idle_cb=mtx.breathe_step, progress_cb=mtx.flash)
            for m in matches:
                if m["kind"] in needed and m["addr"] not in have_addrs:
                    print("found", L.KIND_LABEL.get(m["kind"], m["kind"]), "- connecting...")
                    slot, dev = puck.connect(m["addr_type"], m["addr"], m["kind"])
                    if dev:
                        connected[slot] = {"kind": m["kind"], "addr": m["addr"], "dev": dev}
                        print("connected:", L.KIND_LABEL.get(m["kind"], m["kind"]))
                        mtx.set_progress(len(connected))
                        if _buzzer:
                            _buzzer.beep(988, 60)
                        needed = still_needed(puck, connected, behavior.REQUIRED)
                        have_addrs.add(m["addr"])

        # ── RUN: all required devices present ──
        mtx.running()
        print("all required devices connected - running", behavior.NAME)
        if _buzzer:
            _buzzer.beep(1047, 90)
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
            maybe_warn_battery(mtx)
            poll_button()

        if hasattr(behavior, "on_stop"):
            try:
                behavior.on_stop(devlist(connected))
            except Exception as e:
                print("on_stop error:", e)
        print("lost a required device - scanning again")


def main():
    try:
        run_box()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
