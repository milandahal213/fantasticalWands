"""
Behavior registry.

Each behavior lives in its own module and is a class exposing:
    NAME       : str
    REQUIRED   : list[str]   device kinds needed
                 ("single_motor", "double_motor", "color_sensor", "controller")
    tick(devices)            called repeatedly while active (required)
    on_start(devices)        optional
    on_stop(devices)         optional

To add one: drop in behaviors/my_thing.py with such a class, import it here,
and add it to BEHAVIORS. Then set BEHAVIOR = "my_thing" in config.py.
"""
from behaviors.tank_drive import TankDrive
from behaviors.arcade_drive import ArcadeDrive
from behaviors.light_theremin import LightTheremin
from behaviors.spin import Spin

BEHAVIORS = {
    "tank_drive": TankDrive,
    "arcade_drive": ArcadeDrive,
    "light_theremin": LightTheremin,
    "spin": Spin,
}


def get(name):
    return BEHAVIORS.get(name)
