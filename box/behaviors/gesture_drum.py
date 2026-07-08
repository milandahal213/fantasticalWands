"""Gesture Drum Kit — tap, double-tap, shake, bump or drop the double motor and
its IMU gesture fires a different drum note. The left stick shifts the kit pitch."""
from behaviors.util import find, clamp


class GestureDrum:
    NAME = "Gesture Drum Kit"
    REQUIRED = ["double_motor", "controller"]

    # imu gesture id -> base frequency
    # 0 tapped, 1 double-tapped, 2 collision, 3 shake, 4 freefall
    DRUMS = {0: 262, 1: 330, 2: 196, 3: 523, 4: 392}

    def __init__(self):
        self.last = None

    def tick(self, devices):
        m = find(devices, "double_motor")
        ctrl = find(devices, "controller")
        if not m:
            return
        g = m.imu_gesture

        if g is not None and g != self.last and g in self.DRUMS:
            shift = int(ctrl.left or 0) if ctrl else 0     # kit pitch offset
            f = clamp(self.DRUMS[g] + shift, 60, 2000)
            m.beep(frequency=f, count=1)

        # remember what we saw; "no gesture" (-1/255) lets the same one retrigger
        self.last = g
