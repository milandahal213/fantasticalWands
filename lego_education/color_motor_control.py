"""
Control a LEGO Single Motor speed using a LEGO Color Sensor's reflected light.

Brighter surface → faster motor
Darker surface   → slower / stopped motor

Both devices are separate LEGO hubs connected over BLE simultaneously.
"""

import time
from lego_ble import (
    LegoDevice,
    COLOR_SENSOR_NOTIFICATION,
    MOTOR_BITS_LEFT,
    MOTOR_MOVE_CW,
)

# ── Tuning ────────────────────────────────────────────────────────────────────
REFLECT_MIN   = 0      # reflected value at which motor stops
REFLECT_MAX   = 1023   # reflected value at full speed
MOTOR_MIN_SPEED = 10   # slowest the motor runs before stalling
MOTOR_MAX_SPEED = 100
SPEED_DEADBAND  = 3    # ignore changes smaller than this (avoids flooding hub)

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

    # Connect to each hub one at a time (scans cannot overlap).
    # Turn on the motor hub first, then the sensor hub, so they connect in order.
    # After first run, replace None with the exact names printed during scan.
    motor.scan_and_connect()
    sensor.scan_and_connect()

    motor.program_start()
    sensor.program_start()
    sensor.enable_notifications(50)

    # Wait until the color sensor is actually sending data
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
                speed = 0 if reflected <= REFLECT_MIN else _map(
                    reflected, REFLECT_MIN, REFLECT_MAX,
                    MOTOR_MIN_SPEED, MOTOR_MAX_SPEED)

                if abs(speed - last_speed) >= SPEED_DEADBAND:
                    if speed == 0:
                        motor.motor_stop(MOTOR_BITS_LEFT)
                    else:
                        motor.motor_set_speed(MOTOR_BITS_LEFT, speed)
                    print("Reflected: {:4d}  Speed: {:3d}%".format(reflected, speed))
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
