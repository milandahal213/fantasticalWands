"""Behavior 4 — Color Speed Map.
Each color the sensor detects sets a preset speed/direction on the double motor.
"""
from behaviors.util import find

NAME = "Color Speed Map"
DESCRIPTION = "Detected color sets motor speed & direction"
REQUIRED = ["color_sensor", "double_motor"]

# app color int -> speed (signed)
_SPEED = {
    0: 0,      # no color → stop
    1: 80,     # red
    2: 100,    # yellow
    3: -60,    # blue
    4: 50,     # teal
    5: 40,     # green
    6: -40,    # purple
    7: 20,     # white
    8: -80,    # magenta
    9: 70,     # orange
    10: 30,    # azure
}

_state = {"last": None}


def on_start(devices):
    _state["last"] = None


def tick(devices):
    sensor = find(devices, "color_sensor")
    motor = find(devices, "double_motor")
    if not sensor or not motor:
        return
    color = sensor.color
    if color is None or color == _state["last"]:
        return
    _state["last"] = color
    motor.run(_SPEED.get(color, 50))


def on_stop(devices):
    motor = find(devices, "double_motor")
    if motor:
        motor.stop()
