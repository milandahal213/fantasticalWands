"""
lego_ble.py — LEGO Education BLE RPC protocol for MicroPython (the "puck").

Re-implements the slice of the LEGO wire protocol the puck needs: building
command frames, parsing notification frames, and parsing the advertisement
manufacturer data used to match a device to the puck's NFC card.

Depends only on `struct`, so it also imports/tests fine under desktop CPython.

Wire format (little-endian):
  Command frame       : [msg_id:1][payload...]
  Notification frame  : [60:1][len:2][deviceData...]
                        deviceData = concatenated [sub_type:1][fixed struct...]
  Advertisement mfr   : company 0x0397 -> [grp_hi, grp_lo, color, ser_lo, ser_hi]

GATT:
  Service  0000fd02-0000-1000-8000-00805f9b34fb  (== 16-bit 0xFD02)
  Write    0000fd02-0001-1000-8000-00805f9b34fb  (write-without-response)
  Notify   0000fd02-0002-1000-8000-00805f9b34fb
"""

import struct

# ── GATT UUIDs (strings; wrapped in bluetooth.UUID by the BLE layer) ─────────
SERVICE_UUID = "0000fd02-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fd02-0001-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fd02-0002-1000-8000-00805f9b34fb"

LEGO_COMPANY_ID = 0x0397

# ── Product group -> device kind ─────────────────────────────────────────────
KIND_SINGLE = "single_motor"
KIND_DOUBLE = "double_motor"
KIND_COLOR = "color_sensor"
KIND_CONTROLLER = "controller"

PRODUCT_KIND = {
    512: KIND_SINGLE,
    513: KIND_DOUBLE,
    514: KIND_COLOR,
    515: KIND_CONTROLLER,
}
KIND_LABEL = {
    KIND_SINGLE: "Single Motor",
    KIND_DOUBLE: "Double Motor",
    KIND_COLOR: "Color Sensor",
    KIND_CONTROLLER: "Controller",
}

# ── Color codes ──────────────────────────────────────────────────────────────
# The NFC page-5 color byte AND the BLE advertisement color byte both use the
# LEGO firmware numbering, so no translation is needed to MATCH a card.
#   1 magenta 2 purple 3 blue 4 azure 5 teal 6 green 7 yellow 8 orange 9 red 10 white
FW_COLOR_NAME = {
    1: "Magenta", 2: "Purple", 3: "Blue", 4: "Azure", 5: "Teal",
    6: "Green", 7: "Yellow", 8: "Orange", 9: "Red", 10: "White",
}
# name -> raw color code (what's written on a card). "pink" aliases magenta.
COLOR_BY_NAME = {v.lower(): k for k, v in FW_COLOR_NAME.items()}
COLOR_BY_NAME["pink"] = 1
# RGB for the NeoPixels (kept modest so 3 pixels don't blind anyone).
FW_COLOR_RGB = {
    1: (200, 30, 110),   # magenta
    2: (90, 30, 150),    # purple
    3: (0, 90, 200),     # blue
    4: (60, 160, 220),   # azure
    5: (0, 200, 150),    # teal
    6: (60, 170, 40),    # green
    7: (230, 190, 0),    # yellow
    8: (230, 110, 20),   # orange
    9: (210, 30, 30),    # red
    10: (180, 180, 180),  # white
}

# ── The color sensor reports colors in the *app* numbering; translate for it.
_FW_TO_APP = {-1: 0, 0: 0, 1: 8, 2: 6, 3: 3, 4: 10, 5: 4, 6: 5, 7: 2, 8: 9, 9: 1, 10: 7}
APP_COLOR_NAME = {
    0: "No color", 1: "Red", 2: "Yellow", 3: "Blue", 4: "Teal", 5: "Green",
    6: "Purple", 7: "White", 8: "Magenta", 9: "Orange", 10: "Azure",
}


def fw_color_to_app(fw):
    return _FW_TO_APP.get(fw, 0)


# ── Outgoing message IDs ─────────────────────────────────────────────────────
DEVICE_NOTIFICATION_REQUEST = 40
DEVICE_NOTIFICATION = 60
PLAY_BEEP_COMMAND = 112
MOTOR_RUN_COMMAND = 122
MOTOR_STOP_COMMAND = 138
MOTOR_SET_SPEED_COMMAND = 140
MOVEMENT_MOVE_COMMAND = 150
MOVEMENT_MOVE_TANK_COMMAND = 156
MOVEMENT_SET_SPEED_COMMAND = 170
MOVEMENT_STOP_COMMAND = 168

MOTOR_BITS_LEFT = 1
MOTOR_BITS_BOTH = 3
MOTOR_DIR_CW = 0
MOTOR_DIR_CCW = 1
MOVE_DIR_FWD = 0
MOVE_DIR_BACK = 1

# ── Sub-notification specs: type -> (struct_fmt, payload_size, field_names) ──
_SUB_IMU = 1
_SUB_CARD = 3
_SUB_MOTOR = 10
_SUB_COLOR = 12
_SUB_CONTROLLER = 15

_SUB_SPECS = {
    0:  ("<BB", 2, ("batteryLevel", "usbPowerState")),
    _SUB_IMU: ("<BBhhhhhhhhh", 20, ("orientation", "yawFace", "yaw", "pitch", "roll",
                                    "ax", "ay", "az", "gx", "gy", "gz")),
    _SUB_CARD: ("<bH", 3, ("color", "serial")),
    4:  ("<B", 1, ("state",)),
    _SUB_MOTOR: ("<BBHhblb", 12, ("motorBitMask", "motorState", "absolutePosition",
                                  "power", "speed", "position", "gesture")),
    _SUB_COLOR: ("<bBHHHHBB", 12, ("color", "reflection", "rawRed", "rawGreen",
                                   "rawBlue", "hue", "saturation", "value")),
    _SUB_CONTROLLER: ("<bbhh", 6, ("leftPercent", "rightPercent", "leftAngle", "rightAngle")),
    16: ("<b", 1, ("gesture",)),
}


def _clampb(v):
    v = int(v)
    return -100 if v < -100 else (100 if v > 100 else v)


def _frame(msg_id, payload=b""):
    return bytes([msg_id]) + payload


def cmd_device_notification_request(delay_ms):
    return _frame(DEVICE_NOTIFICATION_REQUEST, struct.pack("<H", int(delay_ms)))


def cmd_play_beep(pattern=0, frequency=440, count=1):
    return _frame(PLAY_BEEP_COMMAND, struct.pack("<BHB", pattern, frequency, count))


def cmd_motor_run(bit_mask, direction):
    return _frame(MOTOR_RUN_COMMAND, struct.pack("<BB", bit_mask, direction))


def cmd_motor_stop(bit_mask):
    return _frame(MOTOR_STOP_COMMAND, struct.pack("<B", bit_mask))


def cmd_motor_set_speed(bit_mask, speed):
    return _frame(MOTOR_SET_SPEED_COMMAND, struct.pack("<Bb", bit_mask, _clampb(speed)))


def cmd_movement_move(direction):
    return _frame(MOVEMENT_MOVE_COMMAND, struct.pack("<B", direction))


def cmd_movement_move_tank(left, right):
    return _frame(MOVEMENT_MOVE_TANK_COMMAND, struct.pack("<bb", _clampb(left), _clampb(right)))


def cmd_movement_set_speed(speed):
    return _frame(MOVEMENT_SET_SPEED_COMMAND, struct.pack("<b", _clampb(speed)))


def cmd_movement_stop():
    return _frame(MOVEMENT_STOP_COMMAND)


# ── Advertisement parsing ────────────────────────────────────────────────────

def parse_manufacturer(data):
    """LEGO manufacturer payload (company id already stripped) ->
    (product_id, color_code, serial) or None."""
    if data is None or len(data) < 5:
        return None
    product_id = (data[0] << 8) | data[1]
    color_code = data[2]
    serial = data[3] | (data[4] << 8)
    return product_id, color_code, serial


# ── Notification parsing ─────────────────────────────────────────────────────

class Sub:
    def __init__(self, sub_type, fields):
        self.type = sub_type
        self.f = fields


def parse_notification(data):
    """Raw incoming GATT packet -> list of Sub. Card/color colors -> app codes."""
    if len(data) < 3 or data[0] != DEVICE_NOTIFICATION:
        return []
    dev_len = data[1] | (data[2] << 8)
    body = data[3:3 + dev_len]
    out = []
    off = 0
    n = len(body)
    while off < n:
        t = body[off]
        spec = _SUB_SPECS.get(t)
        if spec is None:
            break
        fmt, size, names = spec
        chunk = body[off + 1: off + 1 + size]
        if len(chunk) < size:
            break
        vals = struct.unpack(fmt, chunk)
        fields = {}
        for i in range(len(names)):
            fields[names[i]] = vals[i]
        if t == _SUB_CARD or t == _SUB_COLOR:
            fields["color"] = fw_color_to_app(fields["color"])
        out.append(Sub(t, fields))
        off += 1 + size
    return out


# ── Device model ─────────────────────────────────────────────────────────────

class LegoDevice:
    """Live state + high-level commands for one connected device.
    `send` is a callable(bytes) provided by the BLE layer."""

    def __init__(self, kind, label, send):
        self.kind = kind
        self.label = label
        self._send = send
        self.position = None
        self.speed = None
        self.pos_l = self.pos_r = None
        self.speed_l = self.speed_r = None
        self.yaw = None
        self.left = None
        self.right = None
        self.color = None
        self.reflection = None
        self.card_color = 0
        self.card_serial = 0

    def apply(self, subs):
        for s in subs:
            if s.type == _SUB_MOTOR:
                if self.kind == KIND_DOUBLE:
                    if s.f["motorBitMask"] == MOTOR_BITS_LEFT:
                        self.pos_l, self.speed_l = s.f["position"], s.f["speed"]
                    else:
                        self.pos_r, self.speed_r = s.f["position"], s.f["speed"]
                else:
                    self.position, self.speed = s.f["position"], s.f["speed"]
            elif s.type == _SUB_IMU:
                self.yaw = s.f["yaw"]
            elif s.type == _SUB_CONTROLLER:
                self.left, self.right = s.f["leftPercent"], s.f["rightPercent"]
            elif s.type == _SUB_COLOR:
                self.color, self.reflection = s.f["color"], s.f["reflection"]
            elif s.type == _SUB_CARD:
                self.card_color, self.card_serial = s.f["color"], s.f["serial"]

    # commands
    def request_notifications(self, delay_ms=50):
        self._send(cmd_device_notification_request(delay_ms))

    def beep(self, count=1):
        self._send(cmd_play_beep(count=count))

    def run(self, speed):
        if self.kind == KIND_DOUBLE:
            if speed >= 0:
                self._send(cmd_movement_set_speed(speed))
                self._send(cmd_movement_move(MOVE_DIR_FWD))
            else:
                self._send(cmd_movement_set_speed(-speed))
                self._send(cmd_movement_move(MOVE_DIR_BACK))
        else:
            if speed >= 0:
                self._send(cmd_motor_set_speed(MOTOR_BITS_LEFT, speed))
                self._send(cmd_motor_run(MOTOR_BITS_LEFT, MOTOR_DIR_CW))
            else:
                self._send(cmd_motor_set_speed(MOTOR_BITS_LEFT, -speed))
                self._send(cmd_motor_run(MOTOR_BITS_LEFT, MOTOR_DIR_CCW))

    def move_tank(self, left, right):
        self._send(cmd_movement_move_tank(left, right))

    def stop(self):
        if self.kind == KIND_DOUBLE:
            self._send(cmd_movement_stop())
        else:
            self._send(cmd_motor_stop(MOTOR_BITS_BOTH))
