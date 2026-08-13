"""Light Theremin — color sensor's reflected brightness sets motor speed."""
from behaviors.util import find


class LightTheremin:
    NAME = "Light Theremin"
    REQUIRED = ["color_sensor", "single_motor"]

    def tick(self, devices):
        sensor = find(devices, "color_sensor")
        motor = find(devices, "single_motor")
        if sensor and motor and sensor.reflection is not None:
            motor.run(int((sensor.reflection / 255.0) * 100))

    def on_stop(self, devices):
        motor = find(devices, "single_motor")
        if motor:
            motor.run(0)
