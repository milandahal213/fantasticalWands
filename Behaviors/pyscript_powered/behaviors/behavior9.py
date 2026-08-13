"""Behavior 9 — Color Swing Speed.
The detected color sets how fast the single motor sweeps ±90°. Red is fastest,
green slowest. Show a color to the sensor to change the pace on the fly.
"""
from behaviors.util import find, Swinger

NAME = "Color Swing Speed"
DESCRIPTION = "Color sets swing speed (red fastest · green slowest)"
REQUIRED = ["color_sensor", "single_motor"]

_AMP = 90   # fixed half-swing, degrees

# app color int -> swing speed (%). Red fastest → green slowest.
_SPEED = {
    1: 100,   # Red     – fastest
    9: 85,    # Orange
    2: 70,    # Yellow
    7: 60,    # White
    3: 50,    # Blue
    10: 40,   # Azure
    6: 30,    # Purple
    4: 25,    # Teal
    8: 20,    # Magenta
    5: 12,    # Green   – slowest
}

_swing = Swinger()


def on_start(devices):
    _swing.reset()


def tick(devices):
    sensor = find(devices, "color_sensor")
    motor = find(devices, "single_motor")
    if not sensor or not motor:
        return
    speed = _SPEED.get(sensor.color, 0)   # unknown / no color → hold
    if speed <= 0:
        return
    _swing.update(motor, _AMP, speed)


def on_stop(devices):
    _swing.reset()
    motor = find(devices, "single_motor")
    if motor:
        motor.run_to_position(0, speed=60)
