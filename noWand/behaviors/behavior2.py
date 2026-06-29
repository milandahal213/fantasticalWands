"""
Behavior 2 — Arcade Drive
Right stick = throttle (both motors forward/back).
Left stick  = steering (differential mix left vs right).
Easier to drive in a straight line than tank mode.
"""
import threading
import time

from lelib import controller, doubleMotor

NAME        = "Arcade Drive"
DESCRIPTION = "Right stick = throttle  |  Left stick = steer"
REQUIRED    = [controller, doubleMotor]

_stop = threading.Event()


def start(devices: dict) -> None:
    _stop.clear()
    ctrl  = _find(devices, controller)
    motor = _find(devices, doubleMotor)
    if not ctrl or not motor:
        return
    threading.Thread(target=_loop, args=(ctrl, motor), daemon=True).start()


def stop() -> None:
    _stop.set()


# ── internals ─────────────────────────────────────────────────────────────────

def _find(devices, cls):
    for dev in devices.values():
        if isinstance(dev, cls):
            return dev
    return None


def _clamp(v, lo=-100, hi=100):
    return max(lo, min(hi, v))


def _loop(ctrl, motor):
    try:
        while not _stop.is_set():
            throttle = ctrl.right_position()   # forward / back
            steer    = ctrl.left_position()    # turn amount
            left  = _clamp(throttle + steer)
            right = _clamp(throttle - steer)
            motor.movement_move_tank(left, right)
            time.sleep(0.05)
    finally:
        try:
            motor.stop()
        except Exception:
            pass
