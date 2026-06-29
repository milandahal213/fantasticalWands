"""
lego_ble.py — pure-Python implementation of the LEGO Education BLE RPC protocol.

This re-implements just the slice of the `legoeducation` wire protocol that the
app needs, so it can run inside the browser (PyScript/Pyodide) where the native
`legoeducation` and `bleak` packages cannot. It depends only on `struct`, so it
also runs under plain CPython and can be unit-tested offline.

Wire format (little-endian):
  Outgoing command frame : [msg_id:1][payload...]      (no length prefix on wire)
  Incoming notification   : [60:1][len:2][deviceData...]
                            deviceData = concatenated sub-notifications, each
                            [sub_type:1][fixed-size struct...]

GATT (Web Bluetooth):
  Service  0000FD02-0000-1000-8000-00805F9B34FB   (== 16-bit 0xFD02)
  Write    0000FD02-0001-1000-8000-00805F9B34FB   (write-without-response)
  Notify   0000FD02-0002-1000-8000-00805F9B34FB
"""

import struct

# ── GATT UUIDs ──────────────────────────────────────────────────────────────
SERVICE_UUID = "0000fd02-0000-1000-8000-00805f9b34fb"
SERVICE_SHORT = 0xFD02
WRITE_UUID = "0000fd02-0001-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fd02-0002-1000-8000-00805f9b34fb"

# ── Outgoing message IDs ────────────────────────────────────────────────────
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

# ── Motor / movement enums ──────────────────────────────────────────────────
MOTOR_BITS_LEFT = 1
MOTOR_BITS_RIGHT = 2
MOTOR_BITS_BOTH = 3
MOTOR_DIR_CLOCKWISE = 0
MOTOR_DIR_COUNTERCLOCKWISE = 1
MOVEMENT_DIR_FORWARD = 0
MOVEMENT_DIR_BACKWARD = 1
SOUND_BEEP_SINGLE = 0
SOUND_BEEP_DOUBLE = 1

# ── Sub-notification types (inside deviceData) ──────────────────────────────
_SUB_INFO = 0
_SUB_IMU = 1
_SUB_CARD = 3
_SUB_BUTTON = 4
_SUB_MOTOR = 10
_SUB_COLOR = 12
_SUB_CONTROLLER = 15
_SUB_IMU_GESTURE = 16

# sub_type -> (struct_format, payload_size, field_names)
_SUB_SPECS = {
    _SUB_INFO:        ("<BB",            2,  ("batteryLevel", "usbPowerState")),
    _SUB_IMU:         ("<BBhhhhhhhhh",   20, ("orientation", "yawFace", "yaw", "pitch", "roll",
                                              "accelX", "accelY", "accelZ", "gyroX", "gyroY", "gyroZ")),
    _SUB_CARD:        ("<bH",            3,  ("color", "serial")),
    _SUB_BUTTON:      ("<B",             1,  ("state",)),
    _SUB_MOTOR:       ("<BBHhblb",       12, ("motorBitMask", "motorState", "absolutePosition",
                                              "power", "speed", "position", "gesture")),
    _SUB_COLOR:       ("<bBHHHHBB",      12, ("color", "reflection", "rawRed", "rawGreen",
                                              "rawBlue", "hue", "saturation", "value")),
    _SUB_CONTROLLER:  ("<bbhh",          6,  ("leftPercent", "rightPercent", "leftAngle", "rightAngle")),
    _SUB_IMU_GESTURE: ("<b",             1,  ("gesture",)),
}

# ── Color translation (firmware code -> app code) ───────────────────────────
# Firmware: -1 none,0 black,1 magenta,2 purple,3 blue,4 azure,5 turquoise,
#           6 green,7 yellow,8 orange,9 red,10 white
# App:      0 none,1 red,2 yellow,3 blue,4 teal,5 green,6 purple,7 white,
#           8 magenta,9 orange,10 azure
_FW_TO_APP = {-1: 0, 0: 0, 1: 8, 2: 6, 3: 3, 4: 10, 5: 4, 6: 5, 7: 2, 8: 9, 9: 1, 10: 7}

# App color int -> (name, hex)
COLOR_INFO = {
    0:  ("No color", "#9aa0a6"),
    1:  ("Red",      "#de1a21"),
    2:  ("Yellow",   "#ffd400"),
    3:  ("Blue",     "#006cb8"),
    4:  ("Teal",     "#1de9b6"),
    5:  ("Green",    "#61a836"),
    6:  ("Purple",   "#4b2f91"),
    7:  ("White",    "#f5f5f5"),
    8:  ("Magenta",  "#e4599e"),
    9:  ("Orange",   "#f57d20"),
    10: ("Azure",    "#78bfea"),
}

# App color int -> emoji svg basename (cards only carry these)
COLOR_EMOJI = {
    1: "red", 2: "yellow", 3: "blue", 5: "green",
    6: "purple", 8: "magenta", 9: "orange", 10: "azure",
}


def fw_color_to_app(fw):
    return _FW_TO_APP.get(fw, 0)


# ── Command builders (return bytes) ─────────────────────────────────────────

def _frame(msg_id, payload=b""):
    return bytes([msg_id]) + payload


def cmd_device_notification_request(delay_ms):
    return _frame(DEVICE_NOTIFICATION_REQUEST, struct.pack("<H", int(delay_ms)))


def cmd_play_beep(pattern=SOUND_BEEP_SINGLE, frequency=440, count=1):
    return _frame(PLAY_BEEP_COMMAND, struct.pack("<BHB", int(pattern), int(frequency), int(count)))


def cmd_motor_run(bit_mask, direction):
    return _frame(MOTOR_RUN_COMMAND, struct.pack("<BB", int(bit_mask), int(direction)))


def cmd_motor_stop(bit_mask):
    return _frame(MOTOR_STOP_COMMAND, struct.pack("<B", int(bit_mask)))


def cmd_motor_set_speed(bit_mask, speed):
    return _frame(MOTOR_SET_SPEED_COMMAND, struct.pack("<Bb", int(bit_mask), _clampb(speed)))


def cmd_movement_move(direction):
    return _frame(MOVEMENT_MOVE_COMMAND, struct.pack("<B", int(direction)))


def cmd_movement_move_tank(speed_left, speed_right):
    return _frame(MOVEMENT_MOVE_TANK_COMMAND, struct.pack("<bb", _clampb(speed_left), _clampb(speed_right)))


def cmd_movement_set_speed(speed):
    return _frame(MOVEMENT_SET_SPEED_COMMAND, struct.pack("<b", _clampb(speed)))


def cmd_movement_stop():
    return _frame(MOVEMENT_STOP_COMMAND)


def _clampb(v):
    return max(-100, min(100, int(v)))


# ── Notification parsing ────────────────────────────────────────────────────

class SubNotification:
    """A parsed sub-notification: .type (int), plus named fields as attributes."""
    __slots__ = ("type", "fields")

    def __init__(self, sub_type, fields):
        self.type = sub_type
        self.fields = fields

    def __getattr__(self, name):
        try:
            return self.fields[name]
        except KeyError:
            raise AttributeError(name)


def parse_notification(data):
    """Parse a raw incoming GATT packet (bytes) into a list of SubNotification.

    Returns [] if the packet is not a device notification or is malformed.
    Card and color-sensor color fields are translated to app color codes.
    """
    if len(data) < 3 or data[0] != DEVICE_NOTIFICATION:
        return []
    (dev_len,) = struct.unpack_from("<H", data, 1)
    device_data = data[3:3 + dev_len]

    out = []
    offset = 0
    n = len(device_data)
    while offset < n:
        sub_type = device_data[offset]
        spec = _SUB_SPECS.get(sub_type)
        if spec is None:
            break  # unknown type — cannot know its size, stop (matches library)
        fmt, size, names = spec
        body = device_data[offset + 1: offset + 1 + size]
        if len(body) < size:
            break
        values = struct.unpack(fmt, body)
        fields = dict(zip(names, values))
        if sub_type in (_SUB_CARD, _SUB_COLOR):
            fields["color"] = fw_color_to_app(fields["color"])
        out.append(SubNotification(sub_type, fields))
        offset += 1 + size
    return out


# ── Device model ────────────────────────────────────────────────────────────

KIND_SINGLE = "single_motor"
KIND_DOUBLE = "double_motor"
KIND_COLOR = "color_sensor"
KIND_CONTROLLER = "controller"

KIND_LABEL = {
    KIND_SINGLE: "Single Motor",
    KIND_DOUBLE: "Double Motor",
    KIND_COLOR: "Color Sensor",
    KIND_CONTROLLER: "Controller",
}


def kind_from_name(name):
    """Infer device kind from the advertised BLE name (e.g. '🟥 1234 Single Motor')."""
    n = (name or "").lower()
    if "double motor" in n:
        return KIND_DOUBLE
    if "single motor" in n:
        return KIND_SINGLE
    if "color sensor" in n:
        return KIND_COLOR
    if "controller" in n:
        return KIND_CONTROLLER
    return None


class LegoDevice:
    """Holds live state for one connected device and exposes high-level commands.

    `send` is a callable(bytes) that writes a command frame to the device's
    write characteristic. It is provided by the BLE layer.
    """

    def __init__(self, kind, label, send):
        self.kind = kind
        self.label = label          # unique UI label, e.g. "Single Motor 2"
        self._send = send

        # telemetry (None until first relevant notification)
        self.position = None
        self.speed = None
        self.pos_l = self.pos_r = None
        self.speed_l = self.speed_r = None
        self.yaw = None
        self.left = None            # controller left %
        self.right = None           # controller right %
        self.color = None           # app color int from sensor
        self.reflection = None

        # card state
        self.card_color = 0
        self.card_serial = 0
        self._last_card_serial = 0

    # ── incoming ──
    def apply(self, subs):
        """Update state from a list of SubNotification objects."""
        for s in subs:
            if s.type == _SUB_MOTOR:
                if self.kind == KIND_DOUBLE:
                    idx = 0 if s.motorBitMask == MOTOR_BITS_LEFT else 1
                    if idx == 0:
                        self.pos_l, self.speed_l = s.position, s.speed
                    else:
                        self.pos_r, self.speed_r = s.position, s.speed
                else:
                    self.position, self.speed = s.position, s.speed
            elif s.type == _SUB_IMU:
                self.yaw = s.yaw
            elif s.type == _SUB_CONTROLLER:
                self.left, self.right = s.leftPercent, s.rightPercent
            elif s.type == _SUB_COLOR:
                self.color, self.reflection = s.color, s.reflection
            elif s.type == _SUB_CARD:
                self.card_color, self.card_serial = s.color, s.serial

    def card_tapped(self):
        """Return serial on a *new* card placement, else None (edge-triggered)."""
        cur = self.card_serial
        if cur != self._last_card_serial:
            self._last_card_serial = cur
            if cur != 0:
                return cur
        return None

    @property
    def color_name(self):
        return COLOR_INFO.get(self.color or 0, COLOR_INFO[0])[0]

    # ── outgoing ──
    def request_notifications(self, delay_ms=50):
        self._send(cmd_device_notification_request(delay_ms))

    def beep(self, count=1):
        self._send(cmd_play_beep(count=count))

    def run(self, speed):
        """Run motor(s) continuously at signed speed (-100..100)."""
        if self.kind == KIND_DOUBLE:
            if speed >= 0:
                self._send(cmd_movement_set_speed(speed))
                self._send(cmd_movement_move(MOVEMENT_DIR_FORWARD))
            else:
                self._send(cmd_movement_set_speed(-speed))
                self._send(cmd_movement_move(MOVEMENT_DIR_BACKWARD))
        else:
            mask = MOTOR_BITS_LEFT
            if speed >= 0:
                self._send(cmd_motor_set_speed(mask, speed))
                self._send(cmd_motor_run(mask, MOTOR_DIR_CLOCKWISE))
            else:
                self._send(cmd_motor_set_speed(mask, -speed))
                self._send(cmd_motor_run(mask, MOTOR_DIR_COUNTERCLOCKWISE))

    def move_tank(self, left, right):
        """Double motor only: independent left/right speeds (-100..100)."""
        self._send(cmd_movement_move_tank(left, right))

    def stop(self):
        if self.kind == KIND_DOUBLE:
            self._send(cmd_movement_stop())
        else:
            self._send(cmd_motor_stop(MOTOR_BITS_BOTH))
