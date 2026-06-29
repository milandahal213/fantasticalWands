"""
Behavior loader — discovers all behaviorN.py files in this directory.
Each file must define:
    NAME        str   — display name
    DESCRIPTION str   — one-line description
    REQUIRED    list  — device classes needed (from lelib), e.g. [controller, doubleMotor]
    start(devices: dict) -> None   — begin the behavior loop
    stop()               -> None   — stop cleanly
"""
import importlib
import pathlib

def load_all() -> list:
    """Return behavior modules sorted by filename."""
    here = pathlib.Path(__file__).parent
    mods = []
    for path in sorted(here.glob("behavior*.py")):
        mod = importlib.import_module(f"behaviors.{path.stem}")
        mods.append(mod)
    return mods
