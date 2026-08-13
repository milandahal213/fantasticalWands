"""Parking-Sensor Radar — the single motor slowly sweeps the color sensor back
and forth; the brighter/closer the surface, the faster it beeps."""
import time

from behaviors.util import find


class Radar:
    NAME = "Parking-Sensor Radar"
    REQUIRED = ["single_motor", "color_sensor"]

    SWEEP_MS = 800       # time before reversing the sweep
    SWEEP_SPEED = 40
    BEEP_FAR_MS = 800    # slowest beep (nothing near)
    BEEP_NEAR_MS = 60    # fastest beep (bright/close)

    def __init__(self):
        self.dir = 1
        self.t_sweep = 0
        self.t_beep = 0

    def on_start(self, devices):
        self.t_sweep = time.ticks_ms()
        self.t_beep = self.t_sweep

    def tick(self, devices):
        mo = find(devices, "single_motor")
        s = find(devices, "color_sensor")
        if not mo or not s:
            return
        now = time.ticks_ms()

        if time.ticks_diff(now, self.t_sweep) > self.SWEEP_MS:
            self.dir = -self.dir
            self.t_sweep = now
        mo.run(self.dir * self.SWEEP_SPEED)

        r = s.reflection
        if r is None:
            return
        span = self.BEEP_FAR_MS - self.BEEP_NEAR_MS
        interval = self.BEEP_FAR_MS - int((r / 255.0) * span)
        if time.ticks_diff(now, self.t_beep) > interval:
            mo.beep(frequency=880, count=1)
            self.t_beep = now

    def on_stop(self, devices):
        mo = find(devices, "single_motor")
        if mo:
            mo.run(0)
