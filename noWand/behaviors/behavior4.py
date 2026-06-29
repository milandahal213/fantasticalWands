"""
Behavior 4 — Color Speed Map
Each LEGO card color seen by the sensor maps to a preset motor speed and direction.
Good demo of sensor-driven state machine / color-coded commands.

Color   → speed  direction
Red     →  80    forward
Blue    →  60    backward
Green   →  40    forward
Yellow  → 100    forward
No color→   0    stop
Others  →  50    forward
"""
import threading
import time

from lelib import colorSensor, doubleMotor

NAME        = "Color Speed Map"
DESCRIPTION = "Detected color sets motor speed & direction"
REQUIRED    = [colorSensor, doubleMotor]

_COLOR_SPEED = {
    'Red':      80,
    'Blue':    -60,
    'Green':    40,
    'Yellow':  100,
    'Orange':   70,
    'Purple':  -40,
    'White':    20,
    'Teal':     50,
    'Magenta': -80,
    'Azure':    30,
    'No color':  0,
}
_DEFAULT_SPEED = 50

_stop = threading.Event()


def start(devices: dict) -> None:
    _stop.clear()
    sensor = _find(devices, colorSensor)
    motor  = _find(devices, doubleMotor)
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
    last_color = None
    try:
        while not _stop.is_set():
            color = sensor.detect_color()
            if color != last_color:
                speed = _COLOR_SPEED.get(color, _DEFAULT_SPEED)
                motor.run(speed)
                last_color = color
            time.sleep(0.1)
    finally:
        try:
            motor.stop()
        except Exception:
            pass
