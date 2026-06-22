"""
Control a LEGO Single Motor speed using the Color Sensor's reflected light value.

Brighter surface  → faster motor
Darker surface    → slower motor (stops at very low reflection)

Wiring assumption: single motor on the hub, color sensor also on the hub.
"""

import time
from lego_ble import (
    LegoDevice,
    COLOR_SENSOR_NOTIFICATION,
    MOTOR_BITS_LEFT,
    MOTOR_MOVE_CW,
)

# ── Tuning ────────────────────────────────────────────────────────────────────

# The hub reports reflected light as a 0–1023 uint16.
# Adjust these if your sensor reads differently.
REFLECT_MIN = 0      # below this → motor stopped
REFLECT_MAX = 1023   # at or above this → motor at max speed

MOTOR_MIN_SPEED = 10   # minimum speed when surface is bright enough to move
MOTOR_MAX_SPEED = 100

# Only send a new speed command when the value changes by this much,
# so we don't flood the hub with writes.
SPEED_DEADBAND = 3

# ── Shared state (written by IRQ callback, read by main loop) ─────────────────
_latest_reflected = None   # set by the notification callback


def on_notification(notifications):
    global _latest_reflected
    for n in notifications:
        if n["type"] == COLOR_SENSOR_NOTIFICATION:
            _latest_reflected = n["reflected"]


def _map(value, in_min, in_max, out_min, out_max):
    """Linear map, clamped to [out_min, out_max]."""
    if value <= in_min:
        return out_min
    if value >= in_max:
        return out_max
    return int(out_min + (value - in_min) * (out_max - out_min) / (in_max - in_min))


def main():
    dev = LegoDevice(notification_callback=on_notification)
    dev.scan_and_connect()
    dev.program_start()
    dev.enable_notifications(50)   # 50 ms sensor update rate

    # Wait until the color sensor is detected and sending data
    print("Waiting for color sensor…")
    while _latest_reflected is None:
        time.sleep_ms(50)
    print("Color sensor ready.")

    # Start motor running; we'll update speed continuously
    dev.motor_run(MOTOR_BITS_LEFT, MOTOR_MOVE_CW)

    last_speed = -1
    print("Running — point the color sensor at surfaces of different brightness.")
    print("Press Ctrl-C to stop.\n")

    try:
        while True:
            reflected = _latest_reflected
            if reflected is not None:
                if reflected <= REFLECT_MIN:
                    speed = 0
                else:
                    speed = _map(reflected, REFLECT_MIN, REFLECT_MAX,
                                 MOTOR_MIN_SPEED, MOTOR_MAX_SPEED)

                if abs(speed - last_speed) >= SPEED_DEADBAND:
                    if speed == 0:
                        dev.motor_stop(MOTOR_BITS_LEFT)
                    else:
                        dev.motor_set_speed(MOTOR_BITS_LEFT, speed)
                    print("Reflected: {:4d}  →  Speed: {:3d}%".format(reflected, speed))
                    last_speed = speed

            time.sleep_ms(60)

    except KeyboardInterrupt:
        pass

    print("\nStopping…")
    dev.motor_stop(MOTOR_BITS_LEFT)
    time.sleep_ms(200)
    dev.program_stop()
    dev.disconnect()


main()
