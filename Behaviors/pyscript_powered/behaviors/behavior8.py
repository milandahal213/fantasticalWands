"""Behavior 8 — Color Swing Range.
The detected color sets how wide the single motor swings. Red is the most
extreme, green the least; the motor sweeps ±(that range) at a steady speed.
Show a color to the sensor to change the width on the fly.
"""
from behaviors.util import find, Swinger

NAME = "Color Swing Range"
DESCRIPTION = "Color sets swing width (red widest · green narrowest)"
REQUIRED = ["color_sensor", "single_motor"]

# app color int -> half-swing amplitude (degrees). Red widest → green narrowest.
_RANGE = {
    1: 160,   # Red     – widest
    9: 140,   # Orange
    2: 120,   # Yellow
    7: 100,   # White
    3: 90,    # Blue
    10: 75,   # Azure
    6: 65,    # Purple
    4: 55,    # Teal
    8: 48,    # Magenta
    5: 40,    # Green   – narrowest (still a visible sweep after the ~15° turn margin)
}
_SPEED = 70   # fixed swing speed

_swing = Swinger()


def on_start(devices):
    _swing.reset()


def tick(devices):
    sensor = find(devices, "color_sensor")
    motor = find(devices, "single_motor")
    if not sensor or not motor:
        return
    amp = _RANGE.get(sensor.color, 0)   # unknown / no color → rest
    _swing.update(motor, amp, _SPEED)


def on_stop(devices):
    _swing.reset()
    motor = find(devices, "single_motor")
    if motor:
        motor.run_to_position(0, speed=60)
