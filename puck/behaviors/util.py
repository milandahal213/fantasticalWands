"""Helpers shared by behavior modules."""


def find(devices, kind):
    """First connected device of the given kind, or None."""
    for d in devices:
        if d.kind == kind:
            return d
    return None


def clamp(v, lo=-100, hi=100):
    return lo if v < lo else (hi if v > hi else v)
