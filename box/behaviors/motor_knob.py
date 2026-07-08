"""Motor Knob — back-drive the single motor by hand like a dial; its shaft
position sets the double motor's speed. One motor becomes a controller."""
from behaviors.util import find, clamp


class MotorKnob:
    NAME = "Motor Knob"
    REQUIRED = ["single_motor", "double_motor"]

    SCALE = 3     # motor degrees per 1% output speed (tune for sensitivity)

    def __init__(self):
        self.pos0 = None

    def on_start(self, devices):
        s = find(devices, "single_motor")
        self.pos0 = s.position if (s and s.position is not None) else None

    def tick(self, devices):
        s = find(devices, "single_motor")
        m = find(devices, "double_motor")
        if not s or not m:
            return
        pos = s.position
        if pos is None:
            return
        if self.pos0 is None:
            self.pos0 = pos
        m.run(clamp(int((pos - self.pos0) / self.SCALE)))

    def on_stop(self, devices):
        m = find(devices, "double_motor")
        if m:
            m.stop()
