# Double Motor Example — ESP32-C6 MicroPython
# Connects to two Double Motors sharing the same Connection Card.
# Direct port of doublemotor.py from the PC-side legoeducation library.

import asyncio
import lego_rpc as rpc
from lego_ble import connect_multiple

# ── Update these to match your Connection Card ────────────────────────
CARD_COLOR  = rpc.LEGO_COLOR_GREEN
CARD_SERIAL = '0026'
NUMBER_OF_DOUBLE_MOTORS = 4
# ─────────────────────────────────────────────────────────────────────

async def main():
    # Single scan pass finds both motors, then connects concurrently
    doublemotors = await connect_multiple(
        NUMBER_OF_DOUBLE_MOTORS,
        card_color=CARD_COLOR,
        card_serial=CARD_SERIAL,
        product_id=rpc.PRODUCT_GROUP_DEVICE_DOUBLE_MOTOR,
    )

    # Check all connected
    for i, dm in enumerate(doublemotors):
        if not dm.connected:
            print(f'Error connecting to Double Motor {i}.')
            for d in doublemotors:
                await d.disconnect()
            return

    print(f'All {len(doublemotors)} Double Motors connected.')

    # Example:
    # - go forward for 2 seconds at 80% speed
    # - stop
    # - beep
    # - repeat 4 times (a square with turns would need IMU, simplified here)

    for j in range(4):
        print(f'Side {j + 1}: moving forward…')

        # Start all motors moving (non-blocking)
        for dm in doublemotors:
            await dm.movement_move_for_time(2000, speed=80, blocking=False)

        # Wait for the move to complete
        await asyncio.sleep_ms(2100)

        # Stop all motors
        for dm in doublemotors:
            await dm.movement_stop()

        await asyncio.sleep_ms(100)

    # Beep on all devices
    for dm in doublemotors:
        await dm.beep(pattern=rpc.SOUND_PATTERN_BEEP_UP_MIDDLE_DOWN, frequency=500)

    await asyncio.sleep_ms(1000)

    # Disconnect all
    for dm in doublemotors:
        await dm.disconnect()

    print('Done.')

asyncio.run(main())