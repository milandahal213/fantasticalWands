"""Behavior 1 — Tank Drive.
Controller left stick drives the left motor, right stick drives the right motor.
"""
from behaviors.util import find

NAME = "Tank Drive"
DESCRIPTION = "Left stick → left motor · Right stick → right motor"
REQUIRED = ["controller", "double_motor"]


def tick(devices):
    ctrl = find(devices, "controller")
    motor = find(devices, "double_motor")
    if not ctrl or not motor:
        return
    left = ctrl.left or 0
    right = ctrl.right or 0
    motor.move_tank(left, right)


def on_stop(devices):
    motor = find(devices, "double_motor")
    if motor:
        motor.stop()
