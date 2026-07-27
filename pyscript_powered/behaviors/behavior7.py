"""Behavior 7 — Light-Driven Swing.
The single motor sweeps back and forth between -90° and +90°. The color sensor's
reflected brightness sets how fast it swings: bright = fast, dark = slow.
"""
from behaviors.util import find, clamp, Swinger

NAME = "Light-Driven Swing"
DESCRIPTION = "Reflected brightness → swing speed (motor sweeps ±90°)"
REQUIRED = ["color_sensor", "single_motor"]

_AMP = 90         # fixed half-swing, degrees
_FLOOR = 10       # slowest swing so it never fully freezes in the dark

_swing = Swinger()


def on_start(devices):
    _swing.reset()


def tick(devices):
    sensor = find(devices, "color_sensor")
    motor = find(devices, "single_motor")
    if not sensor or not motor:
        return
    raw = sensor.reflection
    if raw is None:
        return
    speed = clamp(int(raw / 255.0 * 100), _FLOOR, 100)
    _swing.update(motor, _AMP, speed)


def on_stop(devices):
    _swing.reset()
    motor = find(devices, "single_motor")
    if motor:
        motor.run_to_position(0, speed=60)
