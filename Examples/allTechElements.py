# all_devices.py
#
# Single Motor   ← Color Sensor reflection (0-100 → motor speed 0-100%)
# Double Motor   ← Controller left/right levers (tank drive)
# Press Controller button to stop.

import asyncio
import time
import lego_rpc as rpc
from lego_ble import scan_for_devices, LegoDevice

# ── Connection Card ───────────────────────────────────────────────────
CARD_COLOR  = rpc.LEGO_COLOR_GREEN
CARD_SERIAL = '0026'
# ─────────────────────────────────────────────────────────────────────

LOOP_INTERVAL_MS  = 50
MOTOR_DEADBAND    = 3
TANK_DEADBAND     = 2
MOTOR_MIN_SEND_MS = 100
TANK_MIN_SEND_MS  = 80


async def connect_one(product_id, label):
    """Scan and connect, retrying up to 3 times if the device drops."""
    for attempt in range(1, 4):
        devices = await scan_for_devices(
            count=1,
            card_color=CARD_COLOR,
            card_serial=CARD_SERIAL,
            product_id=product_id,
            timeout_ms=15000,
        )
        if not devices:
            print(f"  Could not find {label} (attempt {attempt})!")
            continue

        dev = LegoDevice()
        await dev.connect_device(devices[0])

        if dev.connected:
            print(f"  {label} ready.")
            return dev

        print(f"  {label} connected but not streaming — retrying ({attempt}/3)…")
        await asyncio.sleep_ms(1000)

    print(f"  Failed to connect {label} after 3 attempts.")
    return None


async def safe_send(dev, coro_func, *args, label="device"):
    """Call an async method on a device, ignoring errors if disconnected."""
    if dev is None or not dev.connected:
        return
    try:
        await coro_func(*args)
    except Exception as e:
        print(f"  Send error on {label}: {e}")


async def main():
    print("=== Connecting to all devices ===\n")

    print("[1/4] Single Motor…")
    singlemotor = await connect_one(rpc.PRODUCT_GROUP_DEVICE_SINGLE_MOTOR, "Single Motor")

    print("[2/4] Double Motor…")
    doublemotor = await connect_one(rpc.PRODUCT_GROUP_DEVICE_DOUBLE_MOTOR, "Double Motor")

    print("[3/4] Controller…")
    controller  = await connect_one(rpc.PRODUCT_GROUP_DEVICE_CONTROLLER,   "Controller")

    print("[4/4] Color Sensor…")
    colorsensor = await connect_one(rpc.PRODUCT_GROUP_DEVICE_COLOR_SENSOR,  "Color Sensor")

    # Report status — continue even if double motor failed (other devices still work)
    for label, dev in [("Single Motor", singlemotor), ("Double Motor", doublemotor),
                        ("Controller",  controller),  ("Color Sensor", colorsensor)]:
        status = "OK" if (dev and dev.connected) else "NOT CONNECTED"
        print(f"  {label}: {status}")

    if not controller or not colorsensor:
        print("\nController or Color Sensor missing — cannot run. Aborting.")
        for d in [singlemotor, doublemotor, controller, colorsensor]:
            if d: await d.disconnect()
        return

    print("\n=== Running! ===")
    print("Controller levers → Double Motor")
    print("Color Sensor reflection → Single Motor speed")
    print("Controller button → stop\n")

    await asyncio.sleep_ms(300)

    last_left       = None
    last_right      = None
    last_speed      = None
    last_tank_send  = time.ticks_ms()
    last_motor_send = time.ticks_ms()
    motor_running   = False

    try:
        while True:

            # ── Controller button → stop ──────────────────────────────
            if controller.button.get("pressed", False):
                print("Button pressed — stopping.")
                break

            now = time.ticks_ms()

            # ── Controller levers → Double Motor ──────────────────────
            left_pct  = int(controller.controller.get("leftPercent",  0))
            right_pct = int(controller.controller.get("rightPercent", 0))

            tank_ready    = time.ticks_diff(now, last_tank_send) >= TANK_MIN_SEND_MS
            left_changed  = last_left  is None or abs(left_pct  - last_left)  > TANK_DEADBAND
            right_changed = last_right is None or abs(right_pct - last_right) > TANK_DEADBAND

            if tank_ready and (left_changed or right_changed):
                await safe_send(doublemotor, doublemotor.movement_move_tank,
                                left_pct, right_pct, label="Double Motor")
                last_left      = left_pct
                last_right     = right_pct
                last_tank_send = now
                print(f"Tank L={left_pct:+4d}%  R={right_pct:+4d}%")

            # ── Color Sensor reflection → Single Motor speed ──────────
            reflection  = int(colorsensor.color.get("reflection", 0))
            motor_speed = reflection

            motor_ready   = time.ticks_diff(now, last_motor_send) >= MOTOR_MIN_SEND_MS
            speed_changed = last_speed is None or abs(motor_speed - last_speed) > MOTOR_DEADBAND

            if motor_ready and speed_changed:
                if motor_speed < 5:
                    if motor_running:
                        await safe_send(singlemotor, singlemotor.motor_stop,
                                        rpc.MOTOR_BITS_LEFT, label="Single Motor")
                        motor_running = False
                        print(f"Reflection={reflection:3d}  → motor STOP")
                else:
                    await safe_send(singlemotor, singlemotor.motor_set_speed,
                                    rpc.MOTOR_BITS_LEFT, motor_speed, label="Single Motor")
                    if not motor_running:
                        await safe_send(singlemotor, singlemotor.motor_run,
                                        rpc.MOTOR_BITS_LEFT, label="Single Motor")
                        motor_running = True
                    print(f"Reflection={reflection:3d}  → motor speed {motor_speed}%")

                last_speed      = motor_speed
                last_motor_send = now

            await asyncio.sleep_ms(LOOP_INTERVAL_MS)

    except KeyboardInterrupt:
        pass

    # ── Shutdown ──────────────────────────────────────────────────────
    print("\nStopping all devices…")
    await safe_send(doublemotor, doublemotor.movement_stop,   label="Double Motor")
    await safe_send(singlemotor, singlemotor.motor_stop,
                    rpc.MOTOR_BITS_LEFT, label="Single Motor")
    await safe_send(singlemotor, singlemotor.beep,
                    rpc.SOUND_PATTERN_BEEP_TRIPLE, label="Single Motor")
    await asyncio.sleep_ms(800)

    for d in [singlemotor, doublemotor, controller, colorsensor]:
        if d: await d.disconnect()
    print("Done.")


asyncio.run(main())