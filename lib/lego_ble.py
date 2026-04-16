"""
lego_ble.py - BLE Central driver for LEGO Education devices (MicroPython / ESP32-C6)

Data access matches the official docs:
    controller.sensor.leftPercent / rightPercent
    colorsensor.sensor.color / reflection / rawRed / rawGreen / rawBlue
    singlemotor.motor[0].position
    doublemotor.motor[le.MOTOR_LEFT].position
    doublemotor.motor[le.MOTOR_RIGHT].position
    device.button.pressed

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
            product_id     = (data[0] << 8) | data[1]
            fw_card_color  = data[2]
            card_serial    = data[3] | (data[4] << 8)
            app_card_color = rpc.fw_to_app_color(fw_card_color)
            return product_id, app_card_color, card_serial
    except Exception:
        pass
    return None, None, None


# ---------------------------------------------------------------------------
# Sensor data container
# ---------------------------------------------------------------------------

class _SensorData:
    def __repr__(self):
        return str(self.__dict__)


def _make_motor_data():
    s = _SensorData()
    s.motorBitMask = 0
    s.motorState   = 0
    s.absolutePos  = 0
    s.power        = 0
    s.speed        = 0
    s.position     = 0
    s.gesture      = 0
    return s


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
                pid, app_color, adv_serial_int = _extract_mfr(result)
                if pid is None:
                    continue
                if product_id  is not None and pid       != product_id:
                    continue
                if card_color  is not None and app_color != card_color:
                    continue
                if norm_serial is not None and _norm_serial(adv_serial_int) != norm_serial:
                    continue

                addr = result.device.addr_hex()
                if addr in seen_addrs:
                    continue
                seen_addrs.add(addr)
                found.append(result.device)
                print(f"  [{len(found)}/{count}] addr={addr}  pid={pid}  "
                      f"card_color={app_color}  serial={_norm_serial(adv_serial_int)}")
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

        # Set when device acknowledges notification request (type 41, status 0)
        # OR when first actual DeviceNotification (type 60) arrives.
        # The Double Motor responds with type 41 but sends type 60 only when
        # motors are active — both mean "ready to receive commands".
        self._notification_request_acked = asyncio.Event()

        # sensor
        self.sensor              = _SensorData()
        self.sensor.leftPercent  = 0
        self.sensor.rightPercent = 0
        self.sensor.leftAngle    = 0
        self.sensor.rightAngle   = 0
        self.sensor.color        = rpc.LEGO_COLOR_NOCOLOR
        self.sensor.reflection   = 0
        self.sensor.rawRed       = 0
        self.sensor.rawGreen     = 0
        self.sensor.rawBlue      = 0
        self.sensor.hue          = 0
        self.sensor.saturation   = 0
        self.sensor.value        = 0

        # motor list: index 0 = MOTOR_LEFT, 1 = MOTOR_RIGHT
        self.motor = [_make_motor_data(), _make_motor_data()]

        # button
        self.button         = _SensorData()
        self.button.pressed = False
        self.button.state   = rpc.BUTTON_STATE_RELEASED

        # imu / info
        self.imu_device  = _SensorData()
        self.imu_gesture = _SensorData()
        self.info_device = _SensorData()

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

        await self._notify_char.subscribe(notify=True)
        await asyncio.sleep_ms(300)

        self._notification_request_acked.clear()
        self._notify_task = asyncio.create_task(self._notification_loop())

        # Startup sequence:
        # 1. INFO_REQUEST
        await self._send(rpc.info_request())
        await asyncio.sleep_ms(400)

        # 2. PROGRAM_FLOW_NOTIFICATION(START)
        await self._send(rpc.program_flow_notification(rpc.PROGRAM_ACTION_START))
        await asyncio.sleep_ms(400)

        # 3. DEVICE_NOTIFICATION_REQUEST — wait for ACK (type 41) not just data (type 60)
        #    The Double Motor ACKs immediately but only sends type 60 when motors move.
        for attempt in range(1, 4):
            await self._send(rpc.device_notification_request(100))
            print(f"  Notification request sent (attempt {attempt})…")
            try:
                await asyncio.wait_for_ms(
                    self._notification_request_acked.wait(), 2000)
                print(f"  Ready.")
                break
            except asyncio.TimeoutError:
                print(f"  No ACK yet…")
        else:
            print(f"  Warning: device did not acknowledge notification request.")

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
                if not parsed:
                    continue
                if self._debug:
                    print(f"  [rx] {parsed}")

                t = parsed.get("type")

                # DEVICE_NOTIFICATION_RESPONSE (41) — device acknowledged our
                # notification request. Mark as ready even if no data yet.
                if t == rpc.DEVICE_NOTIFICATION_RESPONSE:
                    if parsed.get("status") == 0:
                        self._notification_request_acked.set()

                # DEVICE_NOTIFICATION (60) — actual sensor/motor data
                elif t == "DeviceNotification":
                    for n in parsed["notifications"]:
                        self._apply(n)
                    self._notification_request_acked.set()

        except asyncio.CancelledError:
            pass

    def _apply(self, n):
        t = n.get("type")

        if t == "MotorNotification":
            mask = n["motorBitMask"]
            idx  = rpc.MOTOR_RIGHT if mask == rpc.MOTOR_BITS_RIGHT else rpc.MOTOR_LEFT
            m = self.motor[idx]
            m.motorBitMask = mask
            m.motorState   = n["motorState"]
            m.absolutePos  = n["absolutePos"]
            m.power        = n["power"]
            m.speed        = n["speed"]
            m.position     = n["position"]
            m.gesture      = n["gesture"]

        elif t == "ControllerNotification":
            self.sensor.leftPercent  = n["leftPercent"]
            self.sensor.rightPercent = n["rightPercent"]
            self.sensor.leftAngle    = n["leftAngle"]
            self.sensor.rightAngle   = n["rightAngle"]

        elif t == "ColorSensorNotification":
            self.sensor.color      = n["color"]
            self.sensor.reflection = n["reflection"]
            self.sensor.rawRed     = n["rawRed"]
            self.sensor.rawGreen   = n["rawGreen"]
            self.sensor.rawBlue    = n["rawBlue"]
            self.sensor.hue        = n["hue"]
            self.sensor.saturation = n["saturation"]
            self.sensor.value      = n["value"]

        elif t == "ButtonStateNotification":
            self.button.state   = n["state"]
            self.button.pressed = n["pressed"]

        elif t == "ImuDeviceNotification":
            self.imu_device.orientation  = n["orientation"]
            self.imu_device.yawFace      = n["yaw_face"]
            self.imu_device.yaw          = n["yaw"]
            self.imu_device.pitch        = n["pitch"]
            self.imu_device.roll         = n["roll"]
            ax, ay, az = n["accel"]
            gx, gy, gz = n["gyro"]
            self.imu_device.accelerometerX = ax
            self.imu_device.accelerometerY = ay
            self.imu_device.accelerometerZ = az
            self.imu_device.gyroscopeX     = gx
            self.imu_device.gyroscopeY     = gy
            self.imu_device.gyroscopeZ     = gz

        elif t == "ImuGestureNotification":
            self.imu_gesture.gesture = n["gesture"]

        elif t == "InfoDeviceNotification":
            self.info_device.batteryLevel  = n["battery_level"]
            self.info_device.UsbPowerState = n["usb_power"]

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def light_color(self, color, pattern=rpc.LIGHT_PATTERN_SOLID, intensity=100, blocking=True):
        await self._send(rpc.light_color(color, pattern, intensity))

    async def beep(self, pattern=rpc.SOUND_PATTERN_BEEP_SINGLE, frequency=440, count=1, blocking=True):
        await self._send(rpc.play_beep(pattern, frequency, count))

    async def stop_beep(self):
        await self._send(rpc.stop_sound())

    async def motor_set_speed(self, speed, motor=rpc.MOTOR_BOTH):
        await self._send(rpc.motor_set_speed(motor, speed))

    async def motor_run(self, direction=rpc.MOTOR_MOVE_DIRECTION_CLOCKWISE,
                        motor=rpc.MOTOR_BOTH, speed=None):
        if speed is not None:
            await self._send(rpc.motor_set_speed(motor, speed))
        await self._send(rpc.motor_run(motor, direction))

    async def motor_run_for_time(self, time_ms, direction=rpc.MOTOR_MOVE_DIRECTION_CLOCKWISE,
                                  motor=rpc.MOTOR_BOTH, speed=None):
        if speed is not None:
            await self._send(rpc.motor_set_speed(motor, speed))
        await self._send(rpc.motor_run_for_time(motor, time_ms, direction))

    async def motor_run_for_degrees(self, degrees, direction=rpc.MOTOR_MOVE_DIRECTION_CLOCKWISE,
                                     motor=rpc.MOTOR_BOTH, speed=None):
        if speed is not None:
            await self._send(rpc.motor_set_speed(motor, speed))
        await self._send(rpc.motor_run_for_degrees(motor, degrees, direction))

    async def motor_stop(self, motor=rpc.MOTOR_BOTH, end_state=rpc.MOTOR_END_STATE_BRAKE):
        await self._send(rpc.motor_stop(motor, end_state))

    async def motor_reset_relative_position(self, motor=rpc.MOTOR_BOTH, position=0):
        await self._send(rpc.motor_reset_relative_position(motor, position))

    async def movement_move(self, direction=rpc.MOVEMENT_DIRECTION_FORWARD, speed=None):
        if speed is not None:
            await self._send(rpc.movement_set_speed(speed))
        await self._send(rpc.movement_move(direction))

    async def movement_move_for_time(self, time_ms, direction=rpc.MOVEMENT_DIRECTION_FORWARD,
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

    async def movement_move_tank_for_degrees(self, degrees, speed_left=50, speed_right=50):
        await self._send(rpc.movement_move_tank_for_degrees(degrees, speed_left, speed_right))

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

    async def imu_reset_yaw_axis(self, value=0):
        await self._send(rpc._msg(rpc.IMU_RESET_YAW_AXIS_COMMAND, "<h", int(value)))

    async def imu_set_yaw_face(self, yaw_face):
        await self._send(rpc._msg(rpc.IMU_SET_YAW_FACE_COMMAND, "<B", yaw_face))


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
