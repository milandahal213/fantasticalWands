"""Line Follower — rides the edge of a line using the color sensor's reflected
brightness. Steers proportionally to how far off the edge it is; beeps if lost."""
from behaviors.util import find, clamp


class LineFollower:
    NAME = "Line Follower"
    REQUIRED = ["color_sensor", "double_motor"]

    THRESHOLD = 50    # reflection at the edge (0-255) — tune to your surface
    BASE = 35         # forward speed
    K = 0.6           # steering gain
    LOST_MARGIN = 8   # near-black / near-white => off the line

    def __init__(self):
        self._lost_beeped = False

    def tick(self, devices):
        s = find(devices, "color_sensor")
        m = find(devices, "double_motor")
        if not s or not m:
            return
        r = s.reflection
        if r is None:
            return
        turn = self.K * (r - self.THRESHOLD)
        m.move_tank(clamp(self.BASE + turn), clamp(self.BASE - turn))

        if r < self.LOST_MARGIN or r > (255 - self.LOST_MARGIN):
            if not self._lost_beeped:
                m.beep(frequency=300, count=1)
                self._lost_beeped = True
        else:
            self._lost_beeped = False

    def on_stop(self, devices):
        m = find(devices, "double_motor")
        if m:
            m.stop()
