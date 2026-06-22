"""
MicroPython BLE driver for LEGO Education devices (ESP32-C6).

Uses only the standard 'bluetooth' module — no aioble or async required.
Supports multiple simultaneous connections (one per LEGO hub).

Usage:
    from lego_ble import LegoDevice, COLOR_RED, MOTOR_BITS_LEFT

    motor  = LegoDevice()
    sensor = LegoDevice()

    motor.scan_and_connect(name_filter="Single Motor")
    sensor.scan_and_connect(name_filter="Color Sensor")

    motor.program_start()
    sensor.program_start()
    sensor.enable_notifications(50)
"""

import bluetooth
import struct
import time

# ── UUIDs ─────────────────────────────────────────────────────────────────────
_SVC_UUID   = bluetooth.UUID("0000FD02-0000-1000-8000-00805F9B34FB")
_WRITE_UUID = bluetooth.UUID("0000FD02-0001-1000-8000-00805F9B34FB")
_NOTIF_UUID = bluetooth.UUID("0000FD02-0002-1000-8000-00805F9B34FB")
_CCCD_UUID  = bluetooth.UUID(0x2902)

_SVC_UUID_BYTES = bytes([0x02, 0xFD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
                          0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB])
_SVC_UUID16 = 0xFD02

# ── BLE IRQ event IDs ─────────────────────────────────────────────────────────
_IRQ_SCAN_RESULT                 = 5
_IRQ_SCAN_DONE                   = 6
_IRQ_PERIPHERAL_CONNECT          = 7
_IRQ_PERIPHERAL_DISCONNECT       = 8
_IRQ_GATTC_SERVICE_RESULT        = 9
_IRQ_GATTC_SERVICE_DONE          = 10
_IRQ_GATTC_CHARACTERISTIC_RESULT = 11
_IRQ_GATTC_CHARACTERISTIC_DONE   = 12
_IRQ_GATTC_DESCRIPTOR_RESULT     = 13
_IRQ_GATTC_DESCRIPTOR_DONE       = 14
_IRQ_GATTC_WRITE_DONE            = 17
_IRQ_GATTC_NOTIFY                = 18

# ── Shared BLE instance & dispatcher ─────────────────────────────────────────
_ble            = bluetooth.BLE()
_ble.active(True)
_registry       = {}   # conn_handle -> LegoDevice
_pending        = None # LegoDevice currently in scan/connect phase
_scan_done_flag = False

def _global_irq(event, data):
    global _scan_done_flag, _pending

    if event == _IRQ_SCAN_RESULT:
        addr_type, addr, adv_type, rssi, adv_data = data
        if _pending is not None and _pending._scan_result is None:
            if _adv_has_lego_service(bytes(adv_data)):
                name = _adv_name(bytes(adv_data))
                nf = _pending._name_filter
                if nf is None or (name and nf.lower() in name.lower()):
                    _pending._scan_result = (addr_type, bytes(addr))

    elif event == _IRQ_SCAN_DONE:
        _scan_done_flag = True

    elif event == _IRQ_PERIPHERAL_CONNECT:
        conn_handle, addr_type, addr = data
        if _pending is not None:
            _pending._conn_handle = conn_handle
            _registry[conn_handle] = _pending

    elif event == _IRQ_PERIPHERAL_DISCONNECT:
        conn_handle = data[0]
        dev = _registry.pop(conn_handle, None)
        if dev is not None:
            dev._conn_handle = None
            print("Disconnected from hub")

    else:
        # Route all GATT events to the right device by conn_handle
        try:
            conn_handle = data[0]
            dev = _registry.get(conn_handle)
            if dev is not None:
                dev._handle_irq(event, data)
        except (IndexError, TypeError):
            pass

_ble.irq(_global_irq)


# ── Advertising helpers ───────────────────────────────────────────────────────

def _adv_has_lego_service(adv_data):
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0 or i + length >= len(adv_data):
            break
        ad_type = adv_data[i + 1]
        ad_val  = adv_data[i + 2 : i + 1 + length]
        if ad_type in (0x02, 0x03):
            for j in range(0, len(ad_val) - 1, 2):
                if struct.unpack_from("<H", ad_val, j)[0] == _SVC_UUID16:
                    return True
        elif ad_type in (0x06, 0x07):
            for j in range(0, len(ad_val) - 15, 16):
                if bytes(ad_val[j : j + 16]) == _SVC_UUID_BYTES:
                    return True
        i += 1 + length
    return False

def _adv_name(adv_data):
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0 or i + length >= len(adv_data):
            break
        ad_type = adv_data[i + 1]
        if ad_type in (0x08, 0x09):  # shortened / complete local name
            try:
                return adv_data[i + 2 : i + 1 + length].decode("utf-8")
            except Exception:
                pass
        i += 1 + length
    return None


# ── RPC message type IDs ──────────────────────────────────────────────────────
INFO_REQUEST                   = 0
INFO_RESPONSE                  = 1
PROGRAM_FLOW_NOTIFICATION      = 32
DEVICE_NOTIFICATION_REQUEST    = 40
DEVICE_NOTIFICATION_RESPONSE   = 41
DEVICE_NOTIFICATION            = 60
LIGHT_COLOR_COMMAND            = 110
PLAY_BEEP_COMMAND              = 112
STOP_SOUND_COMMAND             = 114
MOTOR_RUN_COMMAND              = 122
MOTOR_RUN_FOR_DEGREES_COMMAND  = 124
MOTOR_RUN_FOR_TIME_COMMAND     = 126
MOTOR_SET_SPEED_COMMAND        = 140
MOTOR_STOP_COMMAND             = 138
MOTOR_SET_END_STATE_COMMAND    = 142
MOTOR_SET_ACCELERATION_COMMAND = 144

# Sub-notification IDs
INFO_DEVICE_NOTIFICATION  = 0
IMU_DEVICE_NOTIFICATION   = 1
CARD_NOTIFICATION         = 3
BUTTON_STATE_NOTIFICATION = 4
MOTOR_NOTIFICATION        = 10
COLOR_SENSOR_NOTIFICATION = 12
CONTROLLER_NOTIFICATION   = 15
IMU_GESTURE_NOTIFICATION  = 16

# ── Constants ─────────────────────────────────────────────────────────────────
PROGRAM_ACTION_START = 0
PROGRAM_ACTION_STOP  = 1

MOTOR_BITS_LEFT  = 1
MOTOR_BITS_RIGHT = 2
MOTOR_BITS_BOTH  = 3

MOTOR_MOVE_CW  = 0
MOTOR_MOVE_CCW = 1

MOTOR_END_COAST = 0
MOTOR_END_BRAKE = 1
MOTOR_END_HOLD  = 2

LIGHT_SOLID        = 0
LIGHT_BREATHE      = 1
LIGHT_PULSE        = 2
LIGHT_SHORT_BLINK  = 3
LIGHT_LONG_BLINK   = 4
LIGHT_DOUBLE_BLINK = 5

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


# ── Message serialisation ─────────────────────────────────────────────────────

def _h(t):
    return struct.pack("<B", t)

def msg_info_request():
    return _h(INFO_REQUEST)

def msg_program_flow(action):
    return _h(PROGRAM_FLOW_NOTIFICATION) + struct.pack("<B", action)

def msg_enable_notifications(delay_ms):
    return _h(DEVICE_NOTIFICATION_REQUEST) + struct.pack("<H", delay_ms)

def msg_light_color(color, pattern=LIGHT_SOLID, intensity=100):
    return _h(LIGHT_COLOR_COMMAND) + struct.pack("<bBB", color, pattern, intensity)

def msg_motor_run(motor_bitmask, direction=MOTOR_MOVE_CW):
    return _h(MOTOR_RUN_COMMAND) + struct.pack("<BB", motor_bitmask, direction)

def msg_motor_stop(motor_bitmask):
    return _h(MOTOR_STOP_COMMAND) + struct.pack("<B", motor_bitmask)

def msg_motor_run_for_time(motor_bitmask, time_ms, direction=MOTOR_MOVE_CW):
    return _h(MOTOR_RUN_FOR_TIME_COMMAND) + struct.pack("<BLB", motor_bitmask, time_ms, direction)

def msg_motor_run_for_degrees(motor_bitmask, degrees, direction=MOTOR_MOVE_CW):
    return _h(MOTOR_RUN_FOR_DEGREES_COMMAND) + struct.pack("<BlB", motor_bitmask, degrees, direction)

def msg_motor_set_speed(motor_bitmask, speed):
    return _h(MOTOR_SET_SPEED_COMMAND) + struct.pack("<Bb", motor_bitmask, speed)

def msg_motor_set_end_state(motor_bitmask, end_state):
    return _h(MOTOR_SET_END_STATE_COMMAND) + struct.pack("<Bb", motor_bitmask, end_state)

def msg_motor_set_acceleration(motor_bitmask, accel, decel):
    return _h(MOTOR_SET_ACCELERATION_COMMAND) + struct.pack("<BBB", motor_bitmask, accel, decel)

def msg_play_beep(pattern=0, frequency=440, repetitions=1):
    return _h(PLAY_BEEP_COMMAND) + struct.pack("<BHB", pattern, frequency, repetitions)

def msg_stop_sound():
    return _h(STOP_SOUND_COMMAND)


# ── Notification parser ───────────────────────────────────────────────────────

def parse_notification(data):
    out = []
    if not data:
        return out
    msg_type = data[0]
    if msg_type == DEVICE_NOTIFICATION:
        if len(data) < 3:
            return out
        length = struct.unpack_from("<H", data, 1)[0]
        _parse_inner(data[3 : 3 + length], out)
    else:
        out.append({"type": msg_type, "raw": bytes(data[1:])})
    return out

def _parse_inner(data, out):
    offset = 0
    while offset < len(data):
        sub = data[offset]; offset += 1

        if sub == INFO_DEVICE_NOTIFICATION:
            if offset + 14 > len(data): break
            rm, rn = struct.unpack_from("<BB", data, offset); offset += 2
            rb = struct.unpack_from("<H", data, offset)[0]; offset += 2
            fm, fn = struct.unpack_from("<BB", data, offset); offset += 2
            fb = struct.unpack_from("<H", data, offset)[0]; offset += 2
            bm, bn = struct.unpack_from("<BB", data, offset); offset += 2
            bb = struct.unpack_from("<H", data, offset)[0]; offset += 2
            mp = struct.unpack_from("<H", data, offset)[0]; offset += 2
            pid = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({"type": sub, "rpc": (rm, rn, rb),
                        "firmware": (fm, fn, fb), "bootloader": (bm, bn, bb),
                        "max_packet_size": mp, "product_id": pid})

        elif sub == IMU_DEVICE_NOTIFICATION:
            if offset + 12 > len(data): break
            ro, pi, ya = struct.unpack_from("<hhh", data, offset); offset += 6
            ax, ay, az = struct.unpack_from("<hhh", data, offset); offset += 6
            out.append({"type": sub, "roll": ro, "pitch": pi, "yaw": ya,
                        "accel": (ax, ay, az)})

        elif sub == BUTTON_STATE_NOTIFICATION:
            if offset + 1 > len(data): break
            out.append({"type": sub, "state": data[offset]}); offset += 1

        elif sub == MOTOR_NOTIFICATION:
            if offset + 11 > len(data): break
            bits  = data[offset]; offset += 1
            state = data[offset]; offset += 1
            apos  = struct.unpack_from("<H", data, offset)[0]; offset += 2
            rpos  = struct.unpack_from("<l", data, offset)[0]; offset += 4
            spd   = struct.unpack_from("<b", data, offset)[0]; offset += 1
            pwr   = struct.unpack_from("<b", data, offset)[0]; offset += 1
            gest  = struct.unpack_from("<b", data, offset)[0]; offset += 1
            out.append({"type": sub, "motor_bits": bits, "state": state,
                        "abs_position": apos, "position": rpos,
                        "speed": spd, "power": pwr, "gesture": gest})

        elif sub == COLOR_SENSOR_NOTIFICATION:
            if offset + 11 > len(data): break
            color = struct.unpack_from("<b", data, offset)[0]; offset += 1
            refl  = struct.unpack_from("<H", data, offset)[0]; offset += 2
            amb   = struct.unpack_from("<H", data, offset)[0]; offset += 2
            r     = struct.unpack_from("<H", data, offset)[0]; offset += 2
            g     = struct.unpack_from("<H", data, offset)[0]; offset += 2
            b_    = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({"type": sub, "color": color, "reflected": refl,
                        "ambient": amb, "rgb": (r, g, b_)})

        elif sub == CARD_NOTIFICATION:
            if offset + 3 > len(data): break
            color  = struct.unpack_from("<b", data, offset)[0]; offset += 1
            serial = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({"type": sub, "color": color, "serial": serial})

        elif sub == CONTROLLER_NOTIFICATION:
            if offset + 6 > len(data): break
            lx = struct.unpack_from("<b", data, offset)[0]; offset += 1
            ly = struct.unpack_from("<b", data, offset)[0]; offset += 1
            rx = struct.unpack_from("<b", data, offset)[0]; offset += 1
            ry = struct.unpack_from("<b", data, offset)[0]; offset += 1
            bt = struct.unpack_from("<H", data, offset)[0]; offset += 2
            out.append({"type": sub, "left": (lx, ly), "right": (rx, ry),
                        "buttons": bt})

        elif sub == IMU_GESTURE_NOTIFICATION:
            if offset + 1 > len(data): break
            out.append({"type": sub,
                        "gesture": struct.unpack_from("<b", data, offset)[0]})
            offset += 1

        else:
            break


# ── LegoDevice ────────────────────────────────────────────────────────────────

class LegoDevice:
    """BLE client for a single LEGO Education hub.

    Multiple instances can be connected simultaneously — they share the
    underlying bluetooth.BLE() instance and route events by conn_handle.

    Call scan_and_connect() sequentially (not concurrently) for each device.
    """

    def __init__(self, notification_callback=None, timeout_ms=10_000):
        self._cb          = notification_callback
        self._timeout_ms  = timeout_ms
        self._name_filter = None

        # Connection state
        self._scan_result  = None
        self._conn_handle  = None

        # GATT handles
        self._svc_start       = None
        self._svc_end         = None
        self._write_handle    = None
        self._notif_handle    = None
        self._notif_def_handle = None
        self._cccd_handle     = None

        # Completion flags
        self._svc_done  = False
        self._char_done = False
        self._desc_done = False

    # ── Per-device IRQ handler (called by global dispatcher) ─────────────────

    def _handle_irq(self, event, data):
        if event == _IRQ_GATTC_SERVICE_RESULT:
            _, start, end, uuid = data
            if uuid == _SVC_UUID:
                self._svc_start = start
                self._svc_end   = end

        elif event == _IRQ_GATTC_SERVICE_DONE:
            self._svc_done = True

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            _, def_h, val_h, props, uuid = data
            if uuid == _WRITE_UUID:
                self._write_handle = val_h
            elif uuid == _NOTIF_UUID:
                self._notif_handle     = val_h
                self._notif_def_handle = def_h

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            self._char_done = True

        elif event == _IRQ_GATTC_DESCRIPTOR_RESULT:
            _, dsc_h, uuid = data
            if uuid == _CCCD_UUID:
                self._cccd_handle = dsc_h

        elif event == _IRQ_GATTC_DESCRIPTOR_DONE:
            self._desc_done = True

        elif event == _IRQ_GATTC_NOTIFY:
            _, val_h, notify_data = data
            if self._cb is not None:
                parsed = parse_notification(bytes(notify_data))
                self._cb(parsed)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _wait(self, flag_fn, timeout_ms=5000, poll_ms=20):
        elapsed = 0
        while not flag_fn():
            time.sleep_ms(poll_ms)
            elapsed += poll_ms
            if elapsed >= timeout_ms:
                raise OSError("BLE operation timed out")

    # ── Connection management ─────────────────────────────────────────────────

    def scan_and_connect(self, name_filter=None):
        """Scan for a LEGO hub and connect.

        name_filter: optional string — hub name must contain this substring.
        Call sequentially for each device (scans cannot overlap).
        """
        global _pending, _scan_done_flag

        self._name_filter  = name_filter
        self._scan_result  = None
        self._conn_handle  = None
        self._svc_start    = None
        self._svc_end      = None
        self._write_handle = None
        self._notif_handle = None
        self._notif_def_handle = None
        self._cccd_handle  = None
        self._svc_done     = False
        self._char_done    = False
        self._desc_done    = False

        label = '"{}"'.format(name_filter) if name_filter else "any LEGO hub"
        print("Scanning for {}…".format(label))

        _pending        = self
        _scan_done_flag = False
        _ble.gap_scan(self._timeout_ms, 30_000, 30_000, True)
        self._wait(lambda: self._scan_result is not None or _scan_done_flag,
                   self._timeout_ms)
        _ble.gap_scan(None)
        _pending = None

        if self._scan_result is None:
            raise OSError("Hub not found: {}".format(label))

        addr_type, addr = self._scan_result
        print("Found, connecting…")
        _pending = self
        _ble.gap_connect(addr_type, addr)
        self._wait(lambda: self._conn_handle is not None)
        _pending = None
        print("Connected (handle={})".format(self._conn_handle))

        # Service discovery
        _ble.gattc_discover_services(self._conn_handle)
        self._wait(lambda: self._svc_done)
        if self._svc_start is None:
            raise OSError("LEGO service not found")

        # Characteristic discovery
        _ble.gattc_discover_characteristics(
            self._conn_handle, self._svc_start, self._svc_end)
        self._wait(lambda: self._char_done)
        if self._write_handle is None or self._notif_handle is None:
            raise OSError("Required characteristics not found")

        # Descriptor discovery — search full service range to reliably find CCCD
        _ble.gattc_discover_descriptors(
            self._conn_handle, self._svc_start, self._svc_end)
        self._wait(lambda: self._desc_done)

        # Subscribe to BLE notifications
        if self._cccd_handle is not None:
            _ble.gattc_write(self._conn_handle, self._cccd_handle,
                             struct.pack("<H", 1), 1)
        else:
            # Fallback: CCCD is almost always value_handle + 1
            print("Warning: CCCD not found via discovery, trying value_handle+1")
            _ble.gattc_write(self._conn_handle, self._notif_handle + 1,
                             struct.pack("<H", 1), 1)
        time.sleep_ms(100)
        print("Ready.")

    def disconnect(self):
        if self._conn_handle is not None:
            _ble.gap_disconnect(self._conn_handle)
            self._wait(lambda: self._conn_handle is None, timeout_ms=3000)

    @property
    def connected(self):
        return self._conn_handle is not None

    # ── Send ──────────────────────────────────────────────────────────────────

    def send(self, data):
        if self._conn_handle is None:
            raise OSError("Not connected")
        _ble.gattc_write(self._conn_handle, self._write_handle, bytes(data), 0)

    # ── High-level commands ───────────────────────────────────────────────────

    def info_request(self):
        self.send(msg_info_request())

    def program_start(self):
        self.send(msg_program_flow(PROGRAM_ACTION_START))

    def program_stop(self):
        self.send(msg_program_flow(PROGRAM_ACTION_STOP))

    def enable_notifications(self, interval_ms=50):
        self.send(msg_enable_notifications(interval_ms))

    def set_light(self, color=COLOR_WHITE, pattern=LIGHT_SOLID, intensity=100):
        self.send(msg_light_color(color, pattern, intensity))

    def motor_run(self, motor_bitmask=MOTOR_BITS_LEFT, direction=MOTOR_MOVE_CW):
        self.send(msg_motor_run(motor_bitmask, direction))

    def motor_stop(self, motor_bitmask=MOTOR_BITS_LEFT):
        self.send(msg_motor_stop(motor_bitmask))

    def motor_run_for_time(self, motor_bitmask, time_ms, direction=MOTOR_MOVE_CW):
        self.send(msg_motor_run_for_time(motor_bitmask, time_ms, direction))

    def motor_run_for_degrees(self, motor_bitmask, degrees, direction=MOTOR_MOVE_CW):
        self.send(msg_motor_run_for_degrees(motor_bitmask, degrees, direction))

    def motor_set_speed(self, motor_bitmask, speed):
        self.send(msg_motor_set_speed(motor_bitmask, speed))

    def motor_set_end_state(self, motor_bitmask, end_state=MOTOR_END_BRAKE):
        self.send(msg_motor_set_end_state(motor_bitmask, end_state))

    def motor_set_acceleration(self, motor_bitmask, accel, decel):
        self.send(msg_motor_set_acceleration(motor_bitmask, accel, decel))

    def play_beep(self, pattern=0, frequency=440, repetitions=1):
        self.send(msg_play_beep(pattern, frequency, repetitions))

    def stop_sound(self):
        self.send(msg_stop_sound())
