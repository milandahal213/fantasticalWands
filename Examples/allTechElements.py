# all_devices.py
#
# Single Motor speed  ← Color Sensor reflection (0–100%)
# Double Motor        ← Controller levers (tank drive)
# Controller button   → stop everything

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
    for attempt in range(1, 4):
        devices = await scan_for_devices(
            count=1, card_color=CARD_COLOR, card_serial=CARD_SERIAL,
            product_id=product_id, timeout_ms=15000,
        )
        if not devices:
            print(f"  Could not find {label} (attempt {attempt})!")
            continue
        dev = LegoDevice()
        await dev.connect_device(devices[0])
        if dev.connected:
            print(f"  {label} ready.")
            return dev
        print(f"  {label} did not stream — retrying ({attempt}/3)…")
        await asyncio.sleep_ms(1000)
    print(f"  Failed to connect {label}.")
    return None


async def safe(coro):
    try:
        await coro
    except Exception as e:
        print(f"  Send error: {e}")


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

    print()
    for label, dev in [("Single Motor", singlemotor), ("Double Motor", doublemotor),
                        ("Controller",  controller),  ("Color Sensor", colorsensor)]:
        print(f"  {label}: {'OK' if dev and dev.connected else 'NOT CONNECTED'}")

    if not (controller and controller.connected and
            colorsensor and colorsensor.connected):
        print("\nController or Color Sensor missing — aborting.")
        for d in [singlemotor, doublemotor, controller, colorsensor]:
            if d: await d.disconnect()
        return

    print("\n=== Running! ===")
    print("Controller levers → Double Motor (tank)")
    print("Color Sensor reflection → Single Motor speed")
    print("Controller button → stop\n")

    await asyncio.sleep_ms(300)

    # Print initial sensor readings to confirm data is flowing
    print(f"Controller: L={controller.sensor.leftPercent}%  R={controller.sensor.rightPercent}%")
    print(f"Color Sensor: reflection={colorsensor.sensor.reflection}  color={colorsensor.sensor.color}\n")

    last_left       = None
    last_right      = None
    last_speed      = None
    last_tank_send  = time.ticks_ms()
    last_motor_send = time.ticks_ms()
    motor_running   = False

    try:
        while True:

            # ── Controller button → stop ──────────────────────────────
            if controller.button.pressed:
                print("Button pressed — stopping.")
                break

            now = time.ticks_ms()

            # ── Controller levers → Double Motor (tank drive) ─────────
            # Matches docs: controller.sensor.leftPercent / rightPercent
            left_raw  = int(controller.sensor.leftPercent)
            right_raw = int(controller.sensor.rightPercent)
            left_pct  = 0 if abs(left_raw)  <= 2 else left_raw
            right_pct = 0 if abs(right_raw) <= 2 else right_raw

            tank_ready    = time.ticks_diff(now, last_tank_send) >= TANK_MIN_SEND_MS
            left_changed  = last_left  is None or abs(left_pct  - last_left)  > TANK_DEADBAND
            right_changed = last_right is None or abs(right_pct - last_right) > TANK_DEADBAND

            if tank_ready and (left_changed or right_changed) and doublemotor and doublemotor.connected:
                await safe(doublemotor.movement_move_tank(left_pct, right_pct))
                last_left      = left_pct
                last_right     = right_pct
                last_tank_send = now
                print(f"Tank L={left_pct:+4d}%  R={right_pct:+4d}%")

            # ── Color Sensor reflection → Single Motor speed ──────────
            # Matches docs: colorsensor.sensor.reflection
            reflection  = int(colorsensor.sensor.reflection)
            motor_speed = reflection  # 1:1 proportional

            motor_ready   = time.ticks_diff(now, last_motor_send) >= MOTOR_MIN_SEND_MS
            speed_changed = last_speed is None or abs(motor_speed - last_speed) > MOTOR_DEADBAND

            if motor_ready and speed_changed and singlemotor and singlemotor.connected:
                if motor_speed < 5:
                    if motor_running:
                        await safe(singlemotor.motor_stop(motor=rpc.MOTOR_LEFT))
                        motor_running = False
                        print(f"Reflection={reflection:3d}  → motor STOP")
                else:
                    await safe(singlemotor.motor_set_speed(motor_speed, motor=rpc.MOTOR_LEFT))
                    if not motor_running:
                        await safe(singlemotor.motor_run(motor=rpc.MOTOR_LEFT))
                        motor_running = True
                    print(f"Reflection={reflection:3d}  → motor {motor_speed}%")
                last_speed      = motor_speed
                last_motor_send = now

            await asyncio.sleep_ms(LOOP_INTERVAL_MS)

    except KeyboardInterrupt:
        pass

    print("\nStopping…")
    if doublemotor and doublemotor.connected:
        await safe(doublemotor.movement_stop())
    if singlemotor and singlemotor.connected:
        await safe(singlemotor.motor_stop(motor=rpc.MOTOR_LEFT))
        await safe(singlemotor.beep(pattern=rpc.SOUND_PATTERN_BEEP_TRIPLE))
    await asyncio.sleep_ms(800)

    for d in [singlemotor, doublemotor, controller, colorsensor]:
        if d: await d.disconnect()
    print("Done.")


asyncio.run(main())