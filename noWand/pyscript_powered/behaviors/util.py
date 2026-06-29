"""Helpers shared by behavior modules."""


def find(devices, kind):
    """Return the first connected device of the given kind, or None."""
    for d in devices:
        if d.kind == kind:
            return d
    return None


def clamp(v, lo=-100, hi=100):
    return max(lo, min(hi, v))
