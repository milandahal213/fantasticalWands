"""Color Gearbox — tap a color to pick a gear (green=full, yellow=half,
red=reverse crawl), then drive with the controller at that scaled speed.
Beeps on each gear change. Uses all three device types."""
from behaviors.util import find, clamp


class ColorGearbox:
    NAME = "Color Gearbox"
    REQUIRED = ["color_sensor", "controller", "double_motor"]

    # app color id -> speed multiplier.  red=1, yellow=2, green=5
    GEARS = {5: 1.0, 2: 0.5, 1: -0.5}

    def __init__(self):
        self.gear = 0.5
        self.last_color = None

    def tick(self, devices):
        s = find(devices, "color_sensor")
        ctrl = find(devices, "controller")
        m = find(devices, "double_motor")
        if not s or not ctrl or not m:
            return

        c = s.color
        if c is not None and c != self.last_color:
            self.last_color = c
            if c in self.GEARS:
                self.gear = self.GEARS[c]
                m.beep(frequency=660, count=1)

        base = (ctrl.right or 0) * self.gear
        turn = (ctrl.left or 0) * self.gear
        m.move_tank(clamp(base + turn), clamp(base - turn))

    def on_stop(self, devices):
        m = find(devices, "double_motor")
        if m:
            m.stop()
