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

load_all() auto-discovers every behavior*.py in this folder, sorted by name.

To add a behavior: drop in behaviorN.py — it's picked up automatically. For
PyScript, also list the new file under [files] in pyscript.toml, because the
in-browser virtual filesystem only contains files that are mounted there (it
can't list the real directory).
"""
import importlib
import pathlib
import re


def _behavior_number(path):
    """Sort key: the integer in 'behaviorN.py' so behavior10 follows behavior9."""
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else 0


def load_all():
    """Import every behavior*.py in this directory, sorted by behavior number.

    Discovery is filesystem-based so new behaviors need no edits here. Under
    PyScript this walks the mounted virtual FS, so it returns exactly the
    behavior files declared in pyscript.toml.
    """
    here = pathlib.Path(__file__).parent
    mods = []
    for path in sorted(here.glob("behavior*.py"), key=_behavior_number):
        mods.append(importlib.import_module(f"behaviors.{path.stem}"))
    return mods
