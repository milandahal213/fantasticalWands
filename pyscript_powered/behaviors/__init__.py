"""
Behavior registry.

Each behavior is its own module (behavior1.py, behavior2.py, ...) exposing:
    NAME        : str
    DESCRIPTION : str
    REQUIRED    : list[str]   device kinds, e.g. ["controller", "double_motor"]
    tick(devices)            : called repeatedly while active (required)
    on_start(devices)        : optional, called once when activated
    on_stop(devices)         : optional, called once when deactivated

Card-tap activation: a behavior at list index i is triggered by tapping the
card whose app color int is (i + 1) — Red=1 -> behavior 1, Yellow=2 -> 2, ...

To add a behavior: drop in behaviorN.py, add its name to MODULE_NAMES below,
and (for PyScript) list the file under [files] in pyscript.toml.
"""
import importlib

MODULE_NAMES = [
    "behavior1",
    "behavior2",
    "behavior3",
    "behavior4",
    "behavior5",
]


def load_all():
    mods = []
    for name in MODULE_NAMES:
        mods.append(importlib.import_module(f"behaviors.{name}"))
    return mods
