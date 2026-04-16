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

    aioble exposes result.manufacturer() as an iterator of (company_id, data_bytes).
    """
    try:
        for company_id, data in result.manufacturer():
            if company_id != _LEGO_COMPANY_ID:
                continue
            # data is the bytes AFTER the 2-byte company ID
            # LEGO payload: [product_group(1), product_device(1), card_color(1), serial_lo(1), serial_hi(1)]
            if len(data) < 5:
                continue
            product_id  = (data[0] << 8) | data[1]
            card_color  = data[2]
            card_serial = data[3] | (data[4] << 8)
            return product_id, card_color, card_serial
    except Exception:
        pass
    return None, None, None


class LegoDevice:
    """
    Async BLE central for a single LEGO Education device.

        dev = LegoDevice()
        await dev.connect(card_color=rpc.LEGO_COLOR_GREEN, card_serial='0026')
        if not dev.connected:
            print('Error connecting')
            return
        await dev.movement_move_for_time(2000, speed=80)
        await dev.disconnect()
    """

    def __init__(self):
        self._connection  = None
        self._write_char  = None
        self._notify_char = None
        self._notify_task = None

        # Live state updated from notifications
        self.motor  = {}   # latest MotorNotification fields
        self.motors = {}   # motor_mask → MotorNotification fields (Double Motor)
        self.sensor = {}   # latest sensor notification fields

    # ------------------------------------------------------------------
    # connect / disconnect
    # ------------------------------------------------------------------

    async def connect(self, card_color=None, card_serial=None,
                      product_id=None, timeout_ms=15000):
        """
        Scan and connect to the first LEGO device matching the card credentials.
        After awaiting, check dev.connected.
        """
        norm_serial = _norm_serial(card_serial)

        desc = ""
        if card_color is not None:
            desc += f" card_color={card_color}"
        if norm_serial is not None:
            desc += f" card_serial={norm_serial}"
        print(f"Scanning for LEGO device{desc}…")

        target = None
        try:
            async with aioble.scan(duration_ms=timeout_ms,
                                   interval_us=30000,
                                   window_us=30000,
                                   active=True) as scanner:
                async for result in scanner:
                    pid, adv_color, adv_serial_int = _extract_mfr(result)

                    # Must have LEGO manufacturer data
                    if pid is None:
                        continue

                    # Optional product_id filter
                    if product_id is not None and pid != product_id:
                        continue

                    # Card color filter
                    if card_color is not None and adv_color != card_color:
                        continue

                    # Card serial filter
                    if norm_serial is not None:
                        if _norm_serial(adv_serial_int) != norm_serial:
                            continue

                    print(f"  Found: name={result.name()}  "
                          f"addr={result.device.addr_hex()}  "
                          f"product_id={pid}  "
                          f"card_color={adv_color}  "
                          f"card_serial={_norm_serial(adv_serial_int)}")
                    target = result.device
                    break

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            print(f"Scan error: {e}")
            return

        if target is None:
            print("No matching LEGO device found.")
            return

        await self._do_connect(target)

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

        # Ask device to send sensor/motor updates every 50 ms
        await self._send(rpc.device_notification_request(50))
        print("Connected.")

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

    # Light / Sound
    async def set_light_color(self, color, pattern=rpc.LIGHT_PATTERN_SOLID, intensity=100):
        await self._send(rpc.light_color(color, pattern, intensity))

    async def beep(self, pattern=rpc.SOUND_PATTERN_BEEP_SINGLE, frequency=440, repetitions=1):
        await self._send(rpc.play_beep(pattern, frequency, repetitions))

    async def stop_sound(self):
        await self._send(rpc.stop_sound())

    # Individual motor
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

    # Double Motor movement
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