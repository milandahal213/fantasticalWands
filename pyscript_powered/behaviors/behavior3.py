"""Behavior 3 — Light Theremin.
Reflected brightness from the color sensor maps to single-motor speed.
Wave a hand over the sensor to vary the spin.
"""
from behaviors.util import find

NAME = "Light Theremin"
DESCRIPTION = "Reflected brightness → motor speed"
REQUIRED = ["color_sensor", "single_motor"]


def tick(devices):
    sensor = find(devices, "color_sensor")
    motor = find(devices, "single_motor")
    if not sensor or not motor:
        return
    raw = sensor.reflection
    if raw is None:
        return
    motor.run(int((raw / 255.0) * 100))


def on_stop(devices):
    motor = find(devices, "single_motor")
    if motor:
        motor.run(0)
