"""Dance — put wheels on a Double Motor and it runs a looping dance routine
(forward, back, spins, wiggles) all on its own. Beeps at the end of each loop."""
import time

from behaviors.util import find


class Dance:
    NAME = "Dance"
    REQUIRED = ["double_motor"]

    # (duration_ms, left_speed, right_speed) — a (0, 0) step pauses + beeps
    STEPS = [
        (500,  60,  60),   # forward
        (500, -60, -60),   # back
        (600,  70, -70),   # spin right
        (600, -70,  70),   # spin left
        (250,  90,  90),   # quick forward
        (250, -90, -90),   # quick back
        (250,  90,  90),
        (250, -90, -90),
        (500,   0,   0),   # pause + beep, then loop
    ]

    def __init__(self):
        self.i = 0
        self.t = 0

    def on_start(self, devices):
        self.i = 0
        self.t = time.ticks_ms()

    def tick(self, devices):
        m = find(devices, "double_motor")
        if not m:
            return
        dur, left, right = self.STEPS[self.i]
        if time.ticks_diff(time.ticks_ms(), self.t) >= dur:
            self.i = (self.i + 1) % len(self.STEPS)
            self.t = time.ticks_ms()
            dur, left, right = self.STEPS[self.i]
            if left == 0 and right == 0:
                m.beep(frequency=880, count=1)
        m.move_tank(left, right)

    def on_stop(self, devices):
        m = find(devices, "double_motor")
        if m:
            m.stop()
