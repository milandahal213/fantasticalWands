"""
Behavior 1 — Tank Drive
Controller left stick drives the left motor, right stick drives the right motor.
Classic tank/skid-steer: push both forward to go straight, opposite to spin in place.
"""
import threading
import time

from lelib import controller, doubleMotor

NAME        = "Tank Drive"
DESCRIPTION = "Left stick → left motor  |  Right stick → right motor"
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


def _loop(ctrl, motor):
    try:
        while not _stop.is_set():
            l = ctrl.left_position()
            r = ctrl.right_position()
            motor.movement_move_tank(l, r)
            time.sleep(0.05)
    finally:
        try:
            motor.stop()
        except Exception:
            pass
