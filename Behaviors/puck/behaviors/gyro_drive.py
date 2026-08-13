"""Gyro Straight-Line Drive — right stick = throttle; the IMU holds heading so
it drives dead straight. Push the left stick to steer (that re-bases heading)."""
from behaviors.util import find, clamp


class GyroDrive:
    NAME = "Gyro Straight-Line Drive"
    REQUIRED = ["controller", "double_motor"]

    K = 0.8              # heading-correction gain (tune on hardware)
    STEER_DEADZONE = 8   # left-stick travel that counts as "manual steering"

    def __init__(self):
        self.yaw0 = None

    def on_start(self, devices):
        m = find(devices, "double_motor")
        self.yaw0 = m.yaw if (m and m.yaw is not None) else None

    def tick(self, devices):
        ctrl = find(devices, "controller")
        m = find(devices, "double_motor")
        if not ctrl or not m:
            return
        throttle = ctrl.right or 0
        steer = ctrl.left or 0
        yaw = m.yaw

        if abs(steer) > self.STEER_DEADZONE or yaw is None:
            # manual steer; keep heading reference fresh for when we let go
            if yaw is not None:
                self.yaw0 = yaw
            m.move_tank(clamp(throttle + steer), clamp(throttle - steer))
        else:
            if self.yaw0 is None:
                self.yaw0 = yaw
            corr = self.K * (yaw - self.yaw0)          # drift error -> correction
            m.move_tank(clamp(throttle - corr), clamp(throttle + corr))

    def on_stop(self, devices):
        m = find(devices, "double_motor")
        if m:
            m.stop()
