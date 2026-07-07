"""Arcade Drive — right stick throttle, left stick steering (differential mix)."""
from behaviors.util import find, clamp


class ArcadeDrive:
    NAME = "Arcade Drive"
    REQUIRED = ["controller", "double_motor"]

    def tick(self, devices):
        ctrl = find(devices, "controller")
        motor = find(devices, "double_motor")
        if ctrl and motor:
            throttle = ctrl.right or 0
            steer = ctrl.left or 0
            motor.move_tank(clamp(throttle + steer), clamp(throttle - steer))

    def on_stop(self, devices):
        motor = find(devices, "double_motor")
        if motor:
            motor.stop()
