"""Behavior 5 — Alarm System.
The color sensor watches for any color. On a trigger it beeps and the double
motor jolts back and forth, then resets after a cooldown.
"""
import time

from behaviors.util import find

NAME = "Alarm System"
DESCRIPTION = "Color detected → beep + motor jolt"
REQUIRED = ["color_sensor", "double_motor"]

_COOLDOWN = 3.0     # seconds between triggers
_SPIN = 1.0         # seconds of jolt per phase

_state = {"last_trigger": 0.0, "phase": None, "phase_end": 0.0}


def on_start(devices):
    _state.update(last_trigger=0.0, phase=None, phase_end=0.0)


def tick(devices):
    sensor = find(devices, "color_sensor")
    motor = find(devices, "double_motor")
    if not sensor or not motor:
        return
    now = time.monotonic()

    # advance an in-progress jolt
    if _state["phase"] == "fwd" and now >= _state["phase_end"]:
        motor.run(-100)
        _state["phase"] = "rev"
        _state["phase_end"] = now + _SPIN
        return
    if _state["phase"] == "rev" and now >= _state["phase_end"]:
        motor.stop()
        _state["phase"] = None
        return
    if _state["phase"] is not None:
        return  # mid-jolt, nothing else to do

    color = sensor.color
    if color and color != 0 and (now - _state["last_trigger"]) > _COOLDOWN:
        _state["last_trigger"] = now
        motor.beep(count=2)
        motor.run(100)
        _state["phase"] = "fwd"
        _state["phase_end"] = now + _SPIN


def on_stop(devices):
    motor = find(devices, "double_motor")
    if motor:
        motor.stop()
    _state["phase"] = None
