"""Tank Drive — controller sticks drive left/right motors independently."""
from behaviors.util import find


class TankDrive:
    NAME = "Tank Drive"
    REQUIRED = ["controller", "double_motor"]

    def tick(self, devices):
        ctrl = find(devices, "controller")
        motor = find(devices, "double_motor")
        if ctrl and motor:
            motor.move_tank(ctrl.left or 0, ctrl.right or 0)

    def on_stop(self, devices):
        motor = find(devices, "double_motor")
        if motor:
            motor.stop()
