"""Behavior 6 — Joystick Mirror.
The single motor mirrors the controller's left stick as a *position*, not a speed.
Push the stick and the shaft turns to a matching angle; center it and it returns
to zero.

The shaft follows the *direction the stick moved* rather than snapping along the
shortest arc — so a fast swing across center sweeps the motor through center too,
instead of cutting around the back.
"""
import lego_ble as L
from behaviors.util import find, clamp

NAME = "Joystick Mirror"
DESCRIPTION = "Left stick position → single motor shaft angle"
REQUIRED = ["controller", "single_motor"]

_SWING = 160      # degrees of shaft travel at full stick deflection (keep < 180)
_SPEED = 80       # how fast the shaft chases the target angle
_DEADBAND = 4     # min target change (deg) before resending — avoids BLE flooding

_last_target = None


def on_start(devices):
    global _last_target
    _last_target = None


def tick(devices):
    global _last_target
    ctrl = find(devices, "controller")
    motor = find(devices, "single_motor")
    if not ctrl or not motor:
        return
    stick = clamp(ctrl.left or 0)                   # -100 .. 100
    target = int(stick / 100.0 * _SWING)            # signed mirror angle
    if _last_target is not None and abs(target - _last_target) < _DEADBAND:
        return
    # Follow the stick's direction: bigger angle → clockwise, smaller → CCW.
    if _last_target is None:
        direction = L.MOTOR_DIR_SHORTEST
    elif target > _last_target:
        direction = L.MOTOR_DIR_CLOCKWISE
    else:
        direction = L.MOTOR_DIR_COUNTERCLOCKWISE
    motor.run_to_position(target, speed=_SPEED, direction=direction)
    _last_target = target


def on_stop(devices):
    global _last_target
    _last_target = None
    motor = find(devices, "single_motor")
    if motor:
        motor.run_to_position(0, speed=_SPEED)      # recenter on stop
