"""Tilt Steering — right stick is throttle, but you steer by physically tilting
the robot: the IMU roll becomes the steering axis."""
from behaviors.util import find, clamp


class TiltSteer:
    NAME = "Tilt Steering"
    REQUIRED = ["controller", "double_motor"]

    K = 0.4    # roll -> steer gain (tune; roll units are hardware-dependent)

    def tick(self, devices):
        ctrl = find(devices, "controller")
        m = find(devices, "double_motor")
        if not ctrl or not m:
            return
        throttle = ctrl.right or 0
        roll = m.roll
        steer = 0 if roll is None else clamp(self.K * roll)
        m.move_tank(clamp(throttle + steer), clamp(throttle - steer))

    def on_stop(self, devices):
        m = find(devices, "double_motor")
        if m:
            m.stop()
