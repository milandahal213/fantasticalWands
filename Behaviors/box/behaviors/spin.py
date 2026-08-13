"""Spin — spin a single motor continuously."""
from behaviors.util import find


class Spin:
    NAME = "Spin"
    REQUIRED = ["single_motor"]

    def tick(self, devices):
        motor = find(devices, "single_motor")
        if motor:
            motor.run(60)

    def on_stop(self, devices):
        motor = find(devices, "single_motor")
        if motor:
            motor.run(0)
