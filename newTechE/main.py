"""
main.py - boots the default behavior: read a local input (analog joystick on
GP26/27, or an I2C sensor on GP4/5) and BROADCAST it to LEGO motors. Tap a
connection card on the NFC reader (GP0/1) to pick which motor(s) to drive.

See broadcast_main.py for the details.
"""

import broadcast_main

if __name__ == "__main__":
    broadcast_main.main()
