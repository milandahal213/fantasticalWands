"""
SPIKE Prime — control Single Motor speed with Color Sensor reflected light.

Brighter surface → faster motor
Darker surface   → slower motor
"""

import time
from lego_ble import (
    LegoDevice,
    COLOR_SENSOR_NOTIFICATION,
    MOTOR_BITS_LEFT,
    MOTOR_MOVE_CW,
)

# ── Tuning ────────────────────────────────────────────────────────────────────
REFLECT_MIN     = 0      # reflected value → minimum motor speed
REFLECT_MAX     = 55000  # reflected value → maximum motor speed
MOTOR_MIN_SPEED = 10
MOTOR_MAX_SPEED = 100
SPEED_DEADBAND  = 3

# ── Shared state ──────────────────────────────────────────────────────────────
_latest_reflected = None

def on_sensor_notification(notifications):
    global _latest_reflected
    for n in notifications:
        if n["type"] == COLOR_SENSOR_NOTIFICATION:
            _latest_reflected = n["reflected"]

def _map(value, in_min, in_max, out_min, out_max):
    if value <= in_min: return out_min
    if value >= in_max: return out_max
    return int(out_min + (value - in_min) * (out_max - out_min) / (in_max - in_min))

def main():
    motor  = LegoDevice()
    sensor = LegoDevice(notification_callback=on_sensor_notification)

    motor.scan_and_connect()
    sensor.scan_and_connect()

    motor.program_start()
    sensor.program_start()
    sensor.enable_notifications(50)

    print("Waiting for color sensor data…")
    while _latest_reflected is None:
        time.sleep_ms(50)
    print("Color sensor ready. Starting motor.")

    motor.motor_run(MOTOR_BITS_LEFT, MOTOR_MOVE_CW)

    last_speed = -1
    print("Running. Press Ctrl-C to stop.\n")

    try:
        while True:
            reflected = _latest_reflected
            if reflected is not None:
                speed = _map(reflected, REFLECT_MIN, REFLECT_MAX,
                             MOTOR_MIN_SPEED, MOTOR_MAX_SPEED)
                if abs(speed - last_speed) >= SPEED_DEADBAND:
                    motor.motor_set_speed(MOTOR_BITS_LEFT, speed)
                    print("Reflected: {:5d}  Speed: {:3d}%".format(reflected, speed))
                    last_speed = speed
            time.sleep_ms(60)

    except KeyboardInterrupt:
        pass

    print("\nStopping…")
    motor.motor_stop(MOTOR_BITS_LEFT)
    time.sleep_ms(200)
    motor.program_stop()
    sensor.program_stop()
    motor.disconnect()
    sensor.disconnect()

main()
