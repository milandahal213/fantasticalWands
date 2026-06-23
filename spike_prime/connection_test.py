"""
SPIKE Prime — connection test for new LEGO hardware.
Copy lego_ble.py and this file to the SPIKE Prime, then run this.
"""

import time
from lego_ble import LegoDevice

def on_notification(notifications):
    for n in notifications:
        print("notification:", n)

dev = LegoDevice(notification_callback=on_notification)

print("Connecting...")
dev.scan_and_connect()

print("Sending info request...")
dev.info_request()
time.sleep_ms(500)

print("Starting program and enabling notifications...")
dev.program_start()
dev.enable_notifications(200)

print("Listening for 5 seconds...")
time.sleep_ms(5000)

dev.program_stop()
dev.disconnect()
print("Done.")
