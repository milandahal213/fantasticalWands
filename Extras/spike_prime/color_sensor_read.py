"""
SPIKE Prime — read one Color Sensor tech element over BLE.

Connects to a single tech element (SPIKE Prime supports one BLE connection
at a time), enables notifications, and prints live color + reflected light.

Move different colored / brighter / darker surfaces in front of the sensor
and watch the values change. Ctrl-C to stop.
"""

import time
from lego_ble import LegoDevice, COLOR_SENSOR_NOTIFICATION

# Firmware color enum -> readable name
COLOR_NAMES = {
    -1: "none", 0: "black", 1: "magenta", 2: "purple", 3: "blue",
    4: "azure", 6: "green", 7: "yellow", 8: "orange", 9: "red", 10: "white",
}

latest = {"color": None, "reflected": None, "rgb": None}


def on_notification(notifications):
    for n in notifications:
        if n["type"] == COLOR_SENSOR_NOTIFICATION:
            latest["color"] = n["color"]
            latest["reflected"] = n["reflected"]
            latest["rgb"] = n["rgb"]


def main():
    sensor = LegoDevice(notification_callback=on_notification)
    sensor.scan_and_connect()
    sensor.program_start()
    sensor.enable_notifications(100)

    print("Waiting for sensor data…")
    while latest["reflected"] is None:
        time.sleep_ms(50)

    print("Reading. Ctrl-C to stop.\n")
    try:
        while True:
            name = COLOR_NAMES.get(latest["color"], "?")
            print("color={:<8} reflected={:<6} rgb={}".format(
                name, latest["reflected"], latest["rgb"]))
            time.sleep_ms(300)
    except KeyboardInterrupt:
        pass

    print("\nStopping…")
    sensor.program_stop()
    sensor.disconnect()


main()
