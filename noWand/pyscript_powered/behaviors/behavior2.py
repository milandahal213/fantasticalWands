"""Behavior 2 — Arcade Drive.
Right stick = throttle (both motors), left stick = steering (differential mix).
"""
from behaviors.util import find, clamp

NAME = "Arcade Drive"
DESCRIPTION = "Right stick = throttle · Left stick = steer"
REQUIRED = ["controller", "double_motor"]


def tick(devices):
    ctrl = find(devices, "controller")
    motor = find(devices, "double_motor")
    if not ctrl or not motor:
        return
    throttle = ctrl.right or 0
    steer = ctrl.left or 0
    motor.move_tank(clamp(throttle + steer), clamp(throttle - steer))


def on_stop(devices):
    motor = find(devices, "double_motor")
    if motor:
        motor.stop()
