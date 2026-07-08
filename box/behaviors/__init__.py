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
from behaviors.gyro_drive import GyroDrive
from behaviors.precision_turn import PrecisionTurn
from behaviors.line_follower import LineFollower
from behaviors.tilt_steer import TiltSteer
from behaviors.motor_knob import MotorKnob
from behaviors.color_gearbox import ColorGearbox
from behaviors.color_soundboard import ColorSoundboard
from behaviors.simon_says import SimonSays
from behaviors.radar import Radar
from behaviors.gesture_drum import GestureDrum

BEHAVIORS = {
    "tank_drive": TankDrive,
    "arcade_drive": ArcadeDrive,
    "light_theremin": LightTheremin,
    "spin": Spin,
    "gyro_drive": GyroDrive,
    "precision_turn": PrecisionTurn,
    "line_follower": LineFollower,
    "tilt_steer": TiltSteer,
    "motor_knob": MotorKnob,
    "color_gearbox": ColorGearbox,
    "color_soundboard": ColorSoundboard,
    "simon_says": SimonSays,
    "radar": Radar,
    "gesture_drum": GestureDrum,
}


def get(name):
    return BEHAVIORS.get(name)
