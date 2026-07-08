"""Precision Turn / Spinout — flick the right stick left or right and the robot
spins in place a fixed amount using the IMU yaw, then beeps when done."""
from behaviors.util import find


class PrecisionTurn:
    NAME = "Precision Turn"
    REQUIRED = ["controller", "double_motor"]

    TURN_UNITS = 90     # yaw delta for one turn (may be deg or deg*scale — tune)
    TRIGGER = 50        # right-stick travel that starts a turn
    SPEED = 40

    def __init__(self):
        self.turning = False
        self.yaw_start = 0
        self.dir = 1

    def tick(self, devices):
        ctrl = find(devices, "controller")
        m = find(devices, "double_motor")
        if not ctrl or not m:
            return
        yaw = m.yaw

        if not self.turning:
            r = ctrl.right or 0
            if yaw is not None and r > self.TRIGGER:
                self._begin(yaw, 1)
            elif yaw is not None and r < -self.TRIGGER:
                self._begin(yaw, -1)
            else:
                m.stop()
        else:
            if yaw is None:
                return
            # NOTE: doesn't handle the ±180 wrap; fine for <180° turns.
            if abs(yaw - self.yaw_start) >= self.TURN_UNITS:
                m.stop()
                m.beep(frequency=880, count=1)
                self.turning = False
            else:
                m.move_tank(self.dir * self.SPEED, -self.dir * self.SPEED)

    def _begin(self, yaw, direction):
        self.turning = True
        self.yaw_start = yaw
        self.dir = direction

    def on_stop(self, devices):
        m = find(devices, "double_motor")
        if m:
            m.stop()
