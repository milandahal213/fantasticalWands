"""
Behavior 5 — Alarm System
The color sensor watches for any non-background color.
When triggered: double motor spins fast, beeps twice, then resets.
Controller button (if connected) silences the alarm manually.
"""
import threading
import time

from lelib import colorSensor, doubleMotor

NAME        = "Alarm System"
DESCRIPTION = "Color detected → motors spin + beep  |  Watches until stopped"
REQUIRED    = [colorSensor, doubleMotor]

_COOLDOWN   = 3.0   # seconds before alarm can trigger again
_ALARM_SPIN = 2.0   # seconds motors run during alarm

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
    last_trigger = 0.0
    try:
        while not _stop.is_set():
            color = sensor.detect_color()
            now   = time.monotonic()
            if color not in ('No color', 'Unknown') and (now - last_trigger) > _COOLDOWN:
                last_trigger = now
                _trigger_alarm(motor)
            time.sleep(0.1)
    finally:
        try:
            motor.stop()
        except Exception:
            pass


def _trigger_alarm(motor):
    try:
        motor.beep(count=2)
    except Exception:
        pass
    try:
        motor.run(100)
        time.sleep(_ALARM_SPIN / 2)
        motor.run(-100)
        time.sleep(_ALARM_SPIN / 2)
        motor.stop()
    except Exception:
        pass
