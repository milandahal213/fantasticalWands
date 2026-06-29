"""
Behavior 3 — Light Theremin
The color sensor's reflected brightness continuously controls the single motor speed.
Wave your hand closer/further to vary the spin — eerily responsive.
Reflection 0 (dark) → motor stopped.  Reflection max → full speed.
"""
import threading
import time

from lelib import colorSensor, singleMotor

NAME        = "Light Theremin"
DESCRIPTION = "Reflected brightness → motor speed  (wave hand over sensor)"
REQUIRED    = [colorSensor, singleMotor]

_stop = threading.Event()


def start(devices: dict) -> None:
    _stop.clear()
    sensor = _find(devices, colorSensor)
    motor  = _find(devices, singleMotor)
    if not sensor or not motor:
        return
    threading.Thread(target=_loop, args=(sensor, motor), daemon=True).start()


def stop() -> None:
    _stop.set()


# ── internals ─────────────────────────────────────────────────────────────────

def _find(devices, cls):
    for dev in devices.values():
        if isinstance(dev, cls):
            return dev
    return None


def _loop(sensor, motor):
    try:
        while not _stop.is_set():
            raw  = sensor.reflection()           # 0–255
            speed = int((raw / 255.0) * 100)     # map to 0–100
            motor.run(speed)
            time.sleep(0.05)
    finally:
        try:
            motor.run(0)
        except Exception:
            pass
