"""Behavior 10 — Joystick Swing Control.
The left stick sets the swing width and the right stick sets the swing speed.
Negative stick values are ignored (treated as zero), so only pushing a stick
'up' has any effect — push both up to get a wide, fast sweep.
"""
from behaviors.util import find, Swinger

NAME = "Joystick Swing Control"
DESCRIPTION = "Left stick = swing width · Right stick = swing speed"
REQUIRED = ["controller", "single_motor"]

_MAX_ANGLE = 160   # half-swing at full left-stick deflection

_swing = Swinger()


def on_start(devices):
    _swing.reset()


def tick(devices):
    ctrl = find(devices, "controller")
    motor = find(devices, "single_motor")
    if not ctrl or not motor:
        return
    left = max(0, ctrl.left or 0)              # ignore negative stick values
    right = max(0, ctrl.right or 0)
    amp = int(left / 100.0 * _MAX_ANGLE)
    speed = right
    if amp <= 0 or speed <= 0:
        return                                 # rest until both sticks are pushed up
    _swing.update(motor, amp, speed)


def on_stop(devices):
    _swing.reset()
    motor = find(devices, "single_motor")
    if motor:
        motor.run_to_position(0, speed=60)
