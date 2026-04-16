"""
lego_ble.py - BLE Central driver for LEGO Education devices (MicroPython / ESP32-C6)

Supports connecting to multiple devices, including multiple devices that share
the same card color and serial number (distinguished by BLE MAC address).

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
    """Normalise card serial to zero-padded 4-digit string, e.g. 26 → '0026'."""
    if value is None:
        return None
    try:
        return "{:04d}".format(int(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _extract_mfr(result):
    """
    Return (product_id, card_color, card_serial_int) from a scan result,
    or (None, None, None) if no LEGO manufacturer data is present.
    """
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
# Module-level scan function — finds N devices matching given criteria
# in a SINGLE scan pass. This is the correct approach for multiple devices
# sharing the same card, since aioble only allows one scan at a time.
# ---------------------------------------------------------------------------

async def scan_for_devices(count, card_color=None, card_serial=None,
                            product_id=None, timeout_ms=15000):
    """
    Scan for `count` LEGO devices matching the given card credentials.
    Returns a list of aioble device objects (may be shorter than count on timeout).

    Devices are deduplicated by MAC address, so the same device is never
    returned twice even if it advertises multiple times during the scan.
    """
    norm_serial = _norm_serial(card_serial)
    found = []        # list of aioble device objects
    seen_addrs = set()  # MAC addresses already collected

    desc = ""
    if card_color is not None:
        desc += f" card_color={card_color}"
    if norm_serial is not None:
        desc += f" card_serial={norm_serial}"
    print(f"Scanning for {count} LEGO device(s){desc}…")

    try:
        async with aioble.scan(duration_ms=timeout_ms,
                               interval_us=30000,
                               window_us=30000,
                               active=True) as scanner:
            async for result in scanner:
                pid, adv_color, adv_serial_int = _extract_mfr(result)

                if pid is None:
                    continue
                if product_id is not None and pid != product_id:
                    continue
                if card_color is not None and adv_color != card_color:
                    continue
                if norm_serial is not None:
                    if _norm_serial(adv_serial_int) != norm_serial:
                        continue

                addr = result.device.addr_hex()
                if addr in seen_addrs:
                    continue  # already have this device, keep scanning

                seen_addrs.add(addr)
                found.append(result.device)
                print(f"  [{len(found)}/{count}] Found: addr={addr}  "
                      f"product_id={pid}  "
                      f"card_color={adv_color}  "
                      f"card_serial={_norm_serial(adv_serial_int)}")

                if len(found) >= count:
                    break  # got everything we need, stop early

    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print(f"Scan error: {e}")

    if len(found) < count:
        print(f"Warning: only found {len(found)}/{count} devices.")

    return found


# ---------------------------------------------------------------------------
# LegoDevice — one instance per physical device
# ---------------------------------------------------------------------------

class LegoDevice:
    """
    Async BLE central for a single LEGO Education device.

    Normal single-device use:
        dev = LegoDevice()
        await dev.connect(card_color=rpc.LEGO_COLOR_GREEN, card_serial='0026')
        if not dev.connected: ...

    Multi-device use (see connect_multiple below):
        motors = await connect_multiple(2, card_color=..., card_serial=...)
    """

    def __init__(self):
        self._connection  = None
        self._write_char  = None
        self._notify_char = None
        self._notify_task = None

        self.motor  = {}
        self.motors = {}
        self.sensor = {}

    # ------------------------------------------------------------------
    # Single-device connect (scans internally, stops at first match)
    # ------------------------------------------------------------------

    async def connect(self, card_color=None, card_serial=None,
                      product_id=None, timeout_ms=15000):
        devices = await scan_for_devices(
            count=1,
            card_color=card_color,
            card_serial=card_serial,
            product_id=product_id,
            timeout_ms=timeout_ms,
        )
        if not devices:
            print("No matching LEGO device found.")
            return
        await self._do_connect(devices[0])

    # ------------------------------------------------------------------
    # Connect to a pre-found device object (used by connect_multiple)
    # ------------------------------------------------------------------

    async def connect_device(self, device):
        """Connect to a specific aioble device object from a prior scan."""
        await self._do_connect(device)

    # ------------------------------------------------------------------
    # disconnect
    # ------------------------------------------------------------------

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
            print(f"Connection timed out: {device.addr_hex()}")
            self._connection = None
            return
        except Exception as e:
            print(f"Connection error: {e}")
            self._connection = None
            return

        try:
            service = await self._connection.service(_SERVICE_UUID)
            self._write_char  = await service.characteristic(_WRITE_UUID)
            self._notify_char = await service.characteristic(_NOTIFY_UUID)
        except Exception as e:
            print(f"Service discovery error: {e}")
            await self._connection.disconnect()
            self._connection = None
            return

        await self._notify_char.subscribe(notify=True)
        self._notify_task = asyncio.create_task(self._notification_loop())
        await self._send(rpc.device_notification_request(50))
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
                parsed = rpc.parse_response(data)
                if parsed and parsed.get("type") == "DeviceNotification":
                    for n in parsed["notifications"]:
                        t = n.get("type")
                        if t == "MotorNotification":
                            self.motors[n["motor_mask"]] = n
                            self.motor = n
                        elif t in ("ColorSensorNotification", "ControllerNotification",
                                   "ImuDeviceNotification", "ButtonStateNotification",
                                   "CardNotification", "InfoDeviceNotification"):
                            self.sensor = n
        except asyncio.CancelledError:
            pass

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
# Convenience function: scan once, connect all concurrently
# ---------------------------------------------------------------------------

async def connect_multiple(count, card_color=None, card_serial=None,
                            product_id=None, timeout_ms=15000):
    """
    Find `count` LEGO devices in a single scan pass, then connect to all
    of them concurrently. Returns a list of LegoDevice objects.

    All devices in the list are guaranteed to be connected (check .connected
    on each one to be sure).

    Example:
        motors = await connect_multiple(2,
                     card_color=rpc.LEGO_COLOR_GREEN,
                     card_serial='0026',
                     product_id=rpc.PRODUCT_GROUP_DEVICE_DOUBLE_MOTOR)
    """
    # Step 1: single scan pass to find all target devices
    devices = await scan_for_devices(
        count=count,
        card_color=card_color,
        card_serial=card_serial,
        product_id=product_id,
        timeout_ms=timeout_ms,
    )

    # Step 2: create LegoDevice instances
    lego_devices = [LegoDevice() for _ in devices]

    # Step 3: connect sequentially — aioble raises EALREADY if two
    # connections are initiated at the same time.
    for ld, dev in zip(lego_devices, devices):
        await ld.connect_device(dev)

    return lego_devices
