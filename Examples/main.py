# Double Motor Example — ESP32-C6 MicroPython
# Direct port of doublemotor.py from the PC-side legoeducation library.
#
# Files needed on the device:
#   lego_rpc.py
#   lego_ble.py
#   this file (run directly from Thonny)

import asyncio
import lego_rpc as rpc
from lego_ble import LegoDevice

# ── Update these to match your Connection Card ────────────────────────
CARD_COLOR  = rpc.LEGO_COLOR_GREEN
CARD_SERIAL = '0026'
# ─────────────────────────────────────────────────────────────────────

async def main():
    # Connect to the Double Motor using the card credentials
    doublemotor = LegoDevice()
    await doublemotor.connect(
        card_color=CARD_COLOR,
        card_serial=CARD_SERIAL,
        product_id=rpc.PRODUCT_GROUP_DEVICE_DOUBLE_MOTOR,
    )

    # Check connection
    if not doublemotor.connected:
        print('Error connecting to Double Motor.')
        return

    print('Connected to Double Motor.')

    # Example:
    # - go forward for 2 seconds at 80% speed
    # - turn 90 degrees to the right
    # - repeat 4 times (a square)

    for j in range(4):
        print(f'Square side {j + 1}: moving forward…')
        await doublemotor.movement_move_for_time(
            2000,
            direction=rpc.MOVEMENT_DIRECTION_FORWARD,
            speed=80,
            blocking=True,   # waits 2000 ms before continuing
        )

        print(f'Square side {j + 1}: turning 90°…')
        await doublemotor.movement_turn_for_degrees(
            90,
            direction=rpc.MOVEMENT_TURN_DIRECTION_RIGHT,
        )
        # Give the IMU-based turn time to complete (~1.5 s at default speed)
        await asyncio.sleep_ms(1500)

    # Beep when done
    await doublemotor.beep(
        pattern=rpc.SOUND_PATTERN_BEEP_UP_MIDDLE_DOWN,
        frequency=500,
    )
    await asyncio.sleep_ms(1000)

    # Disconnect
    await doublemotor.disconnect()
    print('Done.')

asyncio.run(main())