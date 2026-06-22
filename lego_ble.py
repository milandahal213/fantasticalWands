"""
MicroPython BLE driver for LEGO Education devices (ESP32-C6).

Uses aioble (bundled with MicroPython >=1.23) for BLE access.
Install aioble if missing:
    import mip; mip.install("aioble")

Minimal usage:
    import asyncio
    from lego_ble import LegoDevice

    async def main():
        dev = LegoDevice()
        await dev.scan_and_connect()          # scans for the first LEGO hub
        await dev.program_start()             # tell hub a program is running
        await dev.enable_notifications(50)    # 50 ms notification interval
        await dev.set_light(9, 0, 100)        # RED, SOLID, full brightness
        await dev.motor_run(1, 0)             # motor bitmask=1, CW
        await asyncio.sleep(2)
        await dev.motor_stop(1)
        await dev.disconnect()

    asyncio.run(main())
"""

import struct
import asyncio
import bluetooth
import aioble

# ── BLE service / characteristic UUIDs ──────────────────────────────────────
_SVC_UUID   = bluetooth.UUID("0000FD02-0000-1000-8000-00805F9B34FB")
_WRITE_UUID = bluetooth.UUID("0000FD02-0001-1000-8000-00805F9B34FB")
_NOTIF_UUID = bluetooth.UUID("0000FD02-0002-1000-8000-00805F9B34FB")

LEGO_COMPANY_ID = 0x0397  # used only for optional filtering on adv data

# ── RPC message type IDs (from rpc_message.py) ───────────────────────────────
INFO_REQUEST                 = 0
INFO_RESPONSE                = 1
PROGRAM_FLOW_NOTIFICATION    = 32
DEVICE_NOTIFICATION_REQUEST  = 40
DEVICE_NOTIFICATION_RESPONSE = 41
DEVICE_NOTIFICATION          = 60
LIGHT_COLOR_COMMAND          = 110
PLAY_BEEP_COMMAND            = 112
STOP_SOUND_COMMAND           = 114
MOTOR_RUN_COMMAND            = 122
MOTOR_RUN_FOR_DEGREES_COMMAND= 124
MOTOR_RUN_FOR_TIME_COMMAND   = 126
MOTOR_SET_SPEED_COMMAND      = 140
MOTOR_STOP_COMMAND           = 138
MOTOR_SET_END_STATE_COMMAND  = 142
MOTOR_SET_ACCELERATION_COMMAND = 144

# Sub-notification type IDs (inside DeviceNotification payload)
INFO_DEVICE_NOTIFICATION   = 0
IMU_DEVICE_NOTIFICATION    = 1
CARD_NOTIFICATION          = 3
BUTTON_STATE_NOTIFICATION  = 4
MOTOR_NOTIFICATION         = 10
COLOR_SENSOR_NOTIFICATION  = 12
CONTROLLER_NOTIFICATION    = 15
IMU_GESTURE_NOTIFICATION   = 16

# ── Enum constants ───────────────────────────────────────────────────────────
PROGRAM_ACTION_START = 0
PROGRAM_ACTION_STOP  = 1

MOTOR_BITS_LEFT  = 1
MOTOR_BITS_RIGHT = 2
MOTOR_BITS_BOTH  = 3

MOTOR_MOVE_CW    = 0
MOTOR_MOVE_CCW   = 1

MOTOR_END_COAST       = 0
MOTOR_END_BRAKE       = 1
MOTOR_END_HOLD        = 2

LIGHT_SOLID           = 0
LIGHT_BREATHE         = 1
LIGHT_PULSE           = 2
LIGHT_SHORT_BLINK     = 3
LIGHT_LONG_BLINK      = 4
LIGHT_DOUBLE_BLINK    = 5

# LEGO color enum values (firmware side)
COLOR_NONE    = -1
COLOR_BLACK   = 0
COLOR_MAGENTA = 1
COLOR_PURPLE  = 2
COLOR_BLUE    = 3
COLOR_AZURE   = 4
COLOR_GREEN   = 6
COLOR_YELLOW  = 7
COLOR_ORANGE  = 8
COLOR_RED     = 9
COLOR_WHITE   = 10


# ── Message serialisation helpers ────────────────────────────────────────────

def _pack_header(msg_type):
    return struct.pack("<B", msg_type)

def msg_info_request():
    return _pack_header(INFO_REQUEST)

def msg_program_flow(action):
    return _pack_header(PROGRAM_FLOW_NOTIFICATION) + struct.pack("<B", action)

def msg_enable_notifications(delay_ms):
    """delay_ms: interval in milliseconds between device notifications (uint16)."""
    return _pack_header(DEVICE_NOTIFICATION_REQUEST) + struct.pack("<H", delay_ms)

def msg_light_color(color, pattern=LIGHT_SOLID, intensity=100):
    """color: signed byte (use COLOR_* constants). intensity: 0-100."""
    return _pack_header(LIGHT_COLOR_COMMAND) + struct.pack("<bBB", color, pattern, intensity)

def msg_motor_run(motor_bitmask, direction=MOTOR_MOVE_CW):
    return _pack_header(MOTOR_RUN_COMMAND) + struct.pack("<BB", motor_bitmask, direction)

def msg_motor_stop(motor_bitmask):
    return _pack_header(MOTOR_STOP_COMMAND) + struct.pack("<B", motor_bitmask)

def msg_motor_run_for_time(motor_bitmask, time_ms, direction=MOTOR_MOVE_CW):
    return _pack_header(MOTOR_RUN_FOR_TIME_COMMAND) + struct.pack("<BLB", motor_bitmask, time_ms, direction)

def msg_motor_run_for_degrees(motor_bitmask, degrees, direction=MOTOR_MOVE_CW):
    return _pack_header(MOTOR_RUN_FOR_DEGREES_COMMAND) + struct.pack("<BlB", motor_bitmask, degrees, direction)

def msg_motor_set_speed(motor_bitmask, speed):
    """speed: signed byte, -100..100."""
    return _pack_header(MOTOR_SET_SPEED_COMMAND) + struct.pack("<Bb", motor_bitmask, speed)

def msg_motor_set_end_state(motor_bitmask, end_state):
    return _pack_header(MOTOR_SET_END_STATE_COMMAND) + struct.pack("<Bb", motor_bitmask, end_state)

def msg_motor_set_acceleration(motor_bitmask, accel, decel):
    return _pack_header(MOTOR_SET_ACCELERATION_COMMAND) + struct.pack("<BBB", motor_bitmask, accel, decel)

def msg_play_beep(pattern, frequency=440, repetitions=1):
    return _pack_header(PLAY_BEEP_COMMAND) + struct.pack("<BHB", pattern, frequency, repetitions)

def msg_stop_sound():
    return _pack_header(STOP_SOUND_COMMAND)


# ── Notification parser ───────────────────────────────────────────────────────

def parse_notification(data):
    """Parse a raw DeviceNotification payload into a list of dicts.

    Each dict has at least a 'type' key matching one of the
    *_NOTIFICATION constants above, plus type-specific fields.
    Returns an empty list if the data cannot be parsed.
    """
    results = []
    if not data or len(data) < 3:
        return results
    # The outer DeviceNotification starts after a 1-byte header (type=60) and
    # a 2-byte length; we receive only the payload bytes starting after the
    # outer header because the BLE characteristic value IS the full packet.
    # Strip the leading header byte.
    msg_type = data[0]
    if msg_type == DEVICE_NOTIFICATION:
        offset = 1
        length = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        inner = data[offset: offset + length]
        _parse_inner(inner, results)
    else:
        # Could also be a direct response (INFO_RESPONSE, etc.)
        results.append({"type": msg_type, "raw": data[1:]})
    return results


def _parse_inner(data, out):
    """Walk sub-notifications packed inside a DeviceNotification payload."""
    offset = 0
    while offset < len(data):
        if offset + 1 > len(data):
            break
        sub_type = data[offset]
        offset += 1

        if sub_type == INFO_DEVICE_NOTIFICATION:
            # B B H B B H B B H H H  → 14 bytes
            if offset + 14 > len(data):
                break
            rpc_major, rpc_minor = struct.unpack_from("<BB", data, offset); offset += 2
            rpc_build = struct.unpack_from("<H", data, offset)[0]; offset += 2
            fw_major, fw_minor = struct.unpack_from("<BB", data, offset); offset += 2
            fw_build = struct.unpack_from("<H", data, offset)[0]; offset += 2
            bl_major, bl_minor = struct.unpack_from("<BB", data, offset); offset += 2
            bl_build = struct.unpack_from("<H", data, offset)[0]; offset += 2
            max_pkt = struct.unpack_from("<H", data, offset)[0]; offset += 2
            product_id = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({
                "type": INFO_DEVICE_NOTIFICATION,
                "rpc": (rpc_major, rpc_minor, rpc_build),
                "firmware": (fw_major, fw_minor, fw_build),
                "bootloader": (bl_major, bl_minor, bl_build),
                "max_packet_size": max_pkt,
                "product_id": product_id,
            })

        elif sub_type == IMU_DEVICE_NOTIFICATION:
            # roll, pitch, yaw: 3×int16 → 6 bytes; accel x,y,z: 3×int16 → 6 bytes
            if offset + 12 > len(data):
                break
            roll, pitch, yaw = struct.unpack_from("<hhh", data, offset); offset += 6
            ax, ay, az = struct.unpack_from("<hhh", data, offset); offset += 6
            out.append({
                "type": IMU_DEVICE_NOTIFICATION,
                "roll": roll, "pitch": pitch, "yaw": yaw,
                "accel": (ax, ay, az),
            })

        elif sub_type == BUTTON_STATE_NOTIFICATION:
            if offset + 1 > len(data):
                break
            state = data[offset]; offset += 1
            out.append({"type": BUTTON_STATE_NOTIFICATION, "state": state})

        elif sub_type == MOTOR_NOTIFICATION:
            # motor_bits B, state B, abs_pos H, rel_pos l, speed b, power b, gesture b → 11 bytes
            if offset + 11 > len(data):
                break
            bits = data[offset]; offset += 1
            state = data[offset]; offset += 1
            abs_pos = struct.unpack_from("<H", data, offset)[0]; offset += 2
            rel_pos = struct.unpack_from("<l", data, offset)[0]; offset += 4
            speed = struct.unpack_from("<b", data, offset)[0]; offset += 1
            power = struct.unpack_from("<b", data, offset)[0]; offset += 1
            gesture = struct.unpack_from("<b", data, offset)[0]; offset += 1
            out.append({
                "type": MOTOR_NOTIFICATION,
                "motor_bits": bits,
                "state": state,
                "abs_position": abs_pos,
                "position": rel_pos,
                "speed": speed,
                "power": power,
                "gesture": gesture,
            })

        elif sub_type == COLOR_SENSOR_NOTIFICATION:
            # color b, reflected H, ambient H, r H, g H, b_ H → 11 bytes
            if offset + 11 > len(data):
                break
            color = struct.unpack_from("<b", data, offset)[0]; offset += 1
            reflected = struct.unpack_from("<H", data, offset)[0]; offset += 2
            ambient = struct.unpack_from("<H", data, offset)[0]; offset += 2
            r = struct.unpack_from("<H", data, offset)[0]; offset += 2
            g = struct.unpack_from("<H", data, offset)[0]; offset += 2
            b_ = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({
                "type": COLOR_SENSOR_NOTIFICATION,
                "color": color,
                "reflected": reflected,
                "ambient": ambient,
                "rgb": (r, g, b_),
            })

        elif sub_type == CARD_NOTIFICATION:
            # color b, serial H → 3 bytes
            if offset + 3 > len(data):
                break
            color = struct.unpack_from("<b", data, offset)[0]; offset += 1
            serial = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({"type": CARD_NOTIFICATION, "color": color, "serial": serial})

        elif sub_type == CONTROLLER_NOTIFICATION:
            # left_x b, left_y b, right_x b, right_y b, buttons H → 6 bytes
            if offset + 6 > len(data):
                break
            lx = struct.unpack_from("<b", data, offset)[0]; offset += 1
            ly = struct.unpack_from("<b", data, offset)[0]; offset += 1
            rx = struct.unpack_from("<b", data, offset)[0]; offset += 1
            ry = struct.unpack_from("<b", data, offset)[0]; offset += 1
            buttons = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({
                "type": CONTROLLER_NOTIFICATION,
                "left": (lx, ly),
                "right": (rx, ry),
                "buttons": buttons,
            })

        elif sub_type == IMU_GESTURE_NOTIFICATION:
            if offset + 1 > len(data):
                break
            gesture = struct.unpack_from("<b", data, offset)[0]; offset += 1
            out.append({"type": IMU_GESTURE_NOTIFICATION, "gesture": gesture})

        else:
            # Unknown sub-type — cannot continue parsing without knowing size.
            break


# ── LegoDevice class ──────────────────────────────────────────────────────────

class LegoDevice:
    """Async BLE client for a single LEGO Education hub.

    Example:
        dev = LegoDevice()
        await dev.scan_and_connect()
        await dev.program_start()
        await dev.enable_notifications(50)
        # ... send commands ...
        await dev.disconnect()
    """

    def __init__(self, notification_callback=None, timeout_ms=10_000):
        """
        notification_callback: optional coroutine or function called with
            parsed notification list each time the hub sends data.
            Signature: callback(notifications: list)
        timeout_ms: BLE scan / connect timeout in milliseconds.
        """
        self._connection = None
        self._write_char = None
        self._notif_char = None
        self._cb = notification_callback
        self._timeout_ms = timeout_ms

    # ── connection management ────────────────────────────────────────────────

    async def scan_and_connect(self, name_filter=None):
        """Scan for the first LEGO hub and connect to it.

        name_filter: optional string; hub name must contain this substring.
        Raises OSError / asyncio.TimeoutError on failure.
        """
        print("Scanning for LEGO hub…")
        async with aioble.scan(duration_ms=self._timeout_ms,
                               interval_us=30_000, window_us=30_000,
                               active=True) as scanner:
            async for result in scanner:
                uuids = result.services()
                if _SVC_UUID not in uuids:
                    continue
                if name_filter and result.name() and name_filter not in result.name():
                    continue
                print("Found:", result.name(), result.device)
                break
            else:
                raise OSError("No LEGO hub found during scan")

        print("Connecting…")
        self._connection = await result.device.connect(timeout_ms=self._timeout_ms)
        lego_service = await self._connection.service(_SVC_UUID)
        self._write_char = await lego_service.characteristic(_WRITE_UUID)
        self._notif_char = await lego_service.characteristic(_NOTIF_UUID)
        print("Connected to", result.name())

        # Start notification listener task
        asyncio.get_event_loop().create_task(self._notify_loop())

    async def disconnect(self):
        if self._connection:
            await self._connection.disconnect()
            self._connection = None
        self._write_char = None
        self._notif_char = None

    # ── send / receive ───────────────────────────────────────────────────────

    async def send(self, data):
        """Write raw bytes to the hub (no response required)."""
        await self._write_char.write(data, response=False)

    async def _notify_loop(self):
        """Background task: receives all incoming notifications from the hub."""
        try:
            while self._connection and self._connection.is_connected():
                data = await self._notif_char.notified()
                if self._cb is not None:
                    parsed = parse_notification(bytes(data))
                    try:
                        if asyncio.iscoroutinefunction(self._cb):
                            await self._cb(parsed)
                        else:
                            self._cb(parsed)
                    except Exception as e:
                        print("Notification callback error:", e)
        except Exception:
            pass  # connection closed

    # ── high-level commands ──────────────────────────────────────────────────

    async def info_request(self):
        await self.send(msg_info_request())

    async def program_start(self):
        await self.send(msg_program_flow(PROGRAM_ACTION_START))

    async def program_stop(self):
        await self.send(msg_program_flow(PROGRAM_ACTION_STOP))

    async def enable_notifications(self, interval_ms=50):
        """Ask hub to send sensor notifications every interval_ms milliseconds.
        Set to 0 to disable notifications."""
        await self.send(msg_enable_notifications(interval_ms))

    async def set_light(self, color=COLOR_WHITE, pattern=LIGHT_SOLID, intensity=100):
        await self.send(msg_light_color(color, pattern, intensity))

    async def motor_run(self, motor_bitmask=MOTOR_BITS_LEFT, direction=MOTOR_MOVE_CW):
        await self.send(msg_motor_run(motor_bitmask, direction))

    async def motor_stop(self, motor_bitmask=MOTOR_BITS_LEFT):
        await self.send(msg_motor_stop(motor_bitmask))

    async def motor_run_for_time(self, motor_bitmask, time_ms, direction=MOTOR_MOVE_CW):
        await self.send(msg_motor_run_for_time(motor_bitmask, time_ms, direction))

    async def motor_run_for_degrees(self, motor_bitmask, degrees, direction=MOTOR_MOVE_CW):
        await self.send(msg_motor_run_for_degrees(motor_bitmask, degrees, direction))

    async def motor_set_speed(self, motor_bitmask, speed):
        """-100..100"""
        await self.send(msg_motor_set_speed(motor_bitmask, speed))

    async def motor_set_end_state(self, motor_bitmask, end_state=MOTOR_END_BRAKE):
        await self.send(msg_motor_set_end_state(motor_bitmask, end_state))

    async def motor_set_acceleration(self, motor_bitmask, accel, decel):
        await self.send(msg_motor_set_acceleration(motor_bitmask, accel, decel))

    async def play_beep(self, pattern=0, frequency=440, repetitions=1):
        await self.send(msg_play_beep(pattern, frequency, repetitions))

    async def stop_sound(self):
        await self.send(msg_stop_sound())


# ── Quick smoke-test entry point ──────────────────────────────────────────────

async def _demo():
    received = []

    def on_notification(notifications):
        for n in notifications:
            print("  notif:", n)
        received.extend(notifications)

    dev = LegoDevice(notification_callback=on_notification)
    await dev.scan_and_connect()
    await dev.program_start()
    await dev.enable_notifications(50)
    await asyncio.sleep_ms(500)

    # Flash white light
    await dev.set_light(COLOR_WHITE, LIGHT_SOLID, 100)
    await asyncio.sleep_ms(1000)
    await dev.set_light(COLOR_RED, LIGHT_PULSE, 80)
    await asyncio.sleep_ms(2000)

    # Run left motor clockwise for 2 seconds
    await dev.motor_run(MOTOR_BITS_LEFT, MOTOR_MOVE_CW)
    await asyncio.sleep_ms(2000)
    await dev.motor_stop(MOTOR_BITS_LEFT)

    await dev.program_stop()
    await dev.disconnect()
    print("Done. Received", len(received), "notification(s).")


if __name__ == "__main__":
    asyncio.run(_demo())
