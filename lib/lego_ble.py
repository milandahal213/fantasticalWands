"""
lego_ble.py - BLE Central driver for LEGO Education devices (MicroPython / ESP32-C6)

Requires: aioble  (Tools > Manage packages > search "aioble" in Thonny)
"""

import asyncio
import struct
import bluetooth
import aioble
import lego_rpc as rpc

_SERVICE_UUID    = bluetooth.UUID("0000FD02-0000-1000-8000-00805F9B34FB")
_WRITE_UUID      = bluetooth.UUID("0000FD02-0001-1000-8000-00805F9B34FB")
_NOTIFY_UUID     = bluetooth.UUID("0000FD02-0002-1000-8000-00805F9B34FB")
_LEGO_COMPANY_ID = 0x0397


def _norm_serial(value):
    if value is None:
        return None
    try:
        return "{:04d}".format(int(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _extract_mfr(result):
    try:
        for company_id, data in result.manufacturer():
            if company_id != _LEGO_COMPANY_ID:
                continue
            if len(data) < 5:
                continue
            product_id  = (data[0] << 8) | data[1]
            card_color  = data[2]
            card_serial = data[3] | (data[4] << 8)
            return product_id, card_color, card_serial
    except Exception:
        pass
    return None, None, None


# ---------------------------------------------------------------------------
# Module-level scan
# ---------------------------------------------------------------------------

async def scan_for_devices(count, card_color=None, card_serial=None,
                            product_id=None, timeout_ms=15000):
    norm_serial = _norm_serial(card_serial)
    found      = []
    seen_addrs = set()

    desc = ""
    if card_color  is not None: desc += f" card_color={card_color}"
    if norm_serial is not None: desc += f" card_serial={norm_serial}"
    if product_id  is not None: desc += f" product_id={product_id}"
    print(f"Scanning for {count} device(s){desc}…")

    try:
        async with aioble.scan(duration_ms=timeout_ms,
                               interval_us=30000,
                               window_us=30000,
                               active=True) as scanner:
            async for result in scanner:
                pid, adv_color, adv_serial_int = _extract_mfr(result)
                if pid is None:
                    continue
                if product_id  is not None and pid       != product_id:
                    continue
                if card_color  is not None and adv_color != card_color:
                    continue
                if norm_serial is not None and _norm_serial(adv_serial_int) != norm_serial:
                    continue

                addr = result.device.addr_hex()
                if addr in seen_addrs:
                    continue

                seen_addrs.add(addr)
                found.append(result.device)
                print(f"  [{len(found)}/{count}] addr={addr}  pid={pid}  "
                      f"color={adv_color}  serial={_norm_serial(adv_serial_int)}")

                if len(found) >= count:
                    break

    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print(f"Scan error: {e}")

    if len(found) < count:
        print(f"  Warning: only found {len(found)}/{count} devices.")
    return found


# ---------------------------------------------------------------------------
# LegoDevice
# ---------------------------------------------------------------------------

class LegoDevice:

    def __init__(self, debug=False):
        self._connection  = None
        self._write_char  = None
        self._notify_char = None
        self._notify_task = None
        self._debug       = debug
        self._got_first_notification = asyncio.Event()

        # Typed notification slots — one per notification type
        self.motor      = {}
        self.motors     = {}
        self.controller = {}
        self.color      = {}
        self.imu        = {}
        self.button     = {}
        self.card       = {}
        self.info_dev   = {}

    # ------------------------------------------------------------------
    # connect / disconnect
    # ------------------------------------------------------------------

    async def connect(self, card_color=None, card_serial=None,
                      product_id=None, timeout_ms=15000):
        devices = await scan_for_devices(1, card_color=card_color,
                                         card_serial=card_serial,
                                         product_id=product_id,
                                         timeout_ms=timeout_ms)
        if not devices:
            print("No matching device found.")
            return
        await self.connect_device(devices[0])

    async def connect_device(self, device):
        await self._do_connect(device)

    async def disconnect(self):
        if self._notify_task:
            self._notify_task.cancel()
            try:
                await self._notify_task
            except asyncio.CancelledError:
                pass
            self._notify_task = None
        if self._connection:
            try:
                await self._connection.disconnect()
            except Exception:
                pass
            self._connection = None
        print("Disconnected.")

    @property
    def connected(self):
        return self._connection is not None and self._connection.is_connected()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _do_connect(self, device):
        print(f"Connecting to {device.addr_hex()}…")
        try:
            self._connection = await device.connect(timeout_ms=10000)
        except asyncio.TimeoutError:
            print("Connection timed out.")
            self._connection = None
            return
        except Exception as e:
            print(f"Connection error: {e}")
            self._connection = None
            return

        try:
            service           = await self._connection.service(_SERVICE_UUID)
            self._write_char  = await service.characteristic(_WRITE_UUID)
            self._notify_char = await service.characteristic(_NOTIFY_UUID)
        except Exception as e:
            print(f"Service discovery error: {e}")
            await self._connection.disconnect()
            self._connection = None
            return

        # Subscribe first, then start the listener task
        await self._notify_char.subscribe(notify=True)

        # Small settle delay — gives the CCCD write time to complete
        await asyncio.sleep_ms(200)

        self._got_first_notification.clear()
        self._notify_task = asyncio.create_task(self._notification_loop())

        # Send notification request, retry up to 3 times if no data arrives
        for attempt in range(1, 4):
            await self._send(rpc.device_notification_request(50))
            print(f"  Notification request sent (attempt {attempt})…")
            try:
                await asyncio.wait_for_ms(self._got_first_notification.wait(), 2000)
                print(f"  First notification received.")
                break
            except asyncio.TimeoutError:
                print(f"  No response yet…")
        else:
            print(f"  Warning: no notifications after 3 attempts — device may not be streaming.")

        print(f"Connected to {device.addr_hex()}.")

    async def _send(self, msg_bytes):
        if not self.connected or self._write_char is None:
            raise RuntimeError("Not connected")
        await self._write_char.write(msg_bytes, response=False)

    async def _notification_loop(self):
        try:
            while True:
                try:
                    data = await self._notify_char.notified(timeout_ms=30000)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"Notify error: {e}")
                    break

                if self._debug:
                    print(f"  [raw] {data.hex() if hasattr(data, 'hex') else data}")

                parsed = rpc.parse_response(data)
                if not parsed:
                    continue

                if parsed.get("type") == "DeviceNotification":
                    for n in parsed["notifications"]:
                        self._apply(n)
                    # Signal that at least one notification came through
                    self._got_first_notification.set()

        except asyncio.CancelledError:
            pass

    def _apply(self, n):
        t = n.get("type")
        if self._debug:
            print(f"  [notif] {t}: {n}")

        if t == "MotorNotification":
            self.motors[n["motor_mask"]] = n
            self.motor = n
        elif t == "ControllerNotification":
            self.controller = n
        elif t == "ColorSensorNotification":
            self.color = n
        elif t == "ImuDeviceNotification":
            self.imu = n
        elif t == "ButtonStateNotification":
            self.button = n
        elif t == "CardNotification":
            self.card = n
        elif t == "InfoDeviceNotification":
            self.info_dev = n

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def set_light_color(self, color, pattern=rpc.LIGHT_PATTERN_SOLID, intensity=100):
        await self._send(rpc.light_color(color, pattern, intensity))

    async def beep(self, pattern=rpc.SOUND_PATTERN_BEEP_SINGLE, frequency=440, repetitions=1):
        await self._send(rpc.play_beep(pattern, frequency, repetitions))

    async def stop_sound(self):
        await self._send(rpc.stop_sound())

    async def motor_set_speed(self, motor_mask, speed):
        await self._send(rpc.motor_set_speed(motor_mask, speed))

    async def motor_run(self, motor_mask=rpc.MOTOR_BITS_BOTH,
                        direction=rpc.MOTOR_MOVE_DIRECTION_CLOCKWISE, speed=None):
        if speed is not None:
            await self._send(rpc.motor_set_speed(motor_mask, speed))
        await self._send(rpc.motor_run(motor_mask, direction))

    async def motor_run_for_time(self, motor_mask, time_ms,
                                  direction=rpc.MOTOR_MOVE_DIRECTION_CLOCKWISE, speed=None):
        if speed is not None:
            await self._send(rpc.motor_set_speed(motor_mask, speed))
        await self._send(rpc.motor_run_for_time(motor_mask, time_ms, direction))

    async def motor_run_for_degrees(self, motor_mask, degrees,
                                     direction=rpc.MOTOR_MOVE_DIRECTION_CLOCKWISE, speed=None):
        if speed is not None:
            await self._send(rpc.motor_set_speed(motor_mask, speed))
        await self._send(rpc.motor_run_for_degrees(motor_mask, degrees, direction))

    async def motor_stop(self, motor_mask=rpc.MOTOR_BITS_BOTH,
                          end_state=rpc.MOTOR_END_STATE_BRAKE):
        await self._send(rpc.motor_stop(motor_mask, end_state))

    async def motor_reset_relative_position(self, motor_mask=rpc.MOTOR_BITS_BOTH, position=0):
        await self._send(rpc.motor_reset_relative_position(motor_mask, position))

    async def movement_move(self, direction=rpc.MOVEMENT_DIRECTION_FORWARD, speed=None):
        if speed is not None:
            await self._send(rpc.movement_set_speed(speed))
        await self._send(rpc.movement_move(direction))

    async def movement_move_for_time(self, time_ms,
                                      direction=rpc.MOVEMENT_DIRECTION_FORWARD,
                                      speed=None, blocking=True):
        if speed is not None:
            await self._send(rpc.movement_set_speed(speed))
        await self._send(rpc.movement_move_for_time(time_ms, direction))
        if blocking:
            await asyncio.sleep_ms(time_ms)

    async def movement_move_for_degrees(self, degrees,
                                         direction=rpc.MOVEMENT_MOVE_DIRECTION_FORWARD,
                                         speed=None):
        if speed is not None:
            await self._send(rpc.movement_set_speed(speed))
        await self._send(rpc.movement_move_for_degrees(degrees, direction))

    async def movement_move_tank(self, speed_left, speed_right):
        await self._send(rpc.movement_move_tank(speed_left, speed_right))

    async def movement_turn_for_degrees(self, degrees,
                                         direction=rpc.MOVEMENT_TURN_DIRECTION_LEFT,
                                         speed=None):
        if speed is not None:
            await self._send(rpc.movement_set_speed(speed))
        await self._send(rpc.movement_turn_for_degrees(degrees, direction))

    async def movement_stop(self):
        await self._send(rpc.movement_stop())

    async def movement_set_speed(self, speed):
        await self._send(rpc.movement_set_speed(speed))


# ---------------------------------------------------------------------------
# connect_multiple
# ---------------------------------------------------------------------------

async def connect_multiple(count, card_color=None, card_serial=None,
                            product_id=None, timeout_ms=15000):
    devices      = await scan_for_devices(count, card_color=card_color,
                                           card_serial=card_serial,
                                           product_id=product_id,
                                           timeout_ms=timeout_ms)
    lego_devices = [LegoDevice() for _ in devices]
    for ld, dev in zip(lego_devices, devices):
        await ld.connect_device(dev)
    return lego_devices
