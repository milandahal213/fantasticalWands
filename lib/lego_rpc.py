"""
lego_rpc.py - LEGO Education RPC message serialization for MicroPython (ESP32-C6)

All type IDs, constants, and color values match the official PC library exactly.
"""

import struct

# ---------------------------------------------------------------------------
# Message type IDs  (from rpc_message.py verbatim)
# ---------------------------------------------------------------------------
INFO_REQUEST                            = 0
INFO_RESPONSE                           = 1
PROGRAM_FLOW_NOTIFICATION               = 32
DEVICE_NOTIFICATION_REQUEST             = 40
DEVICE_NOTIFICATION_RESPONSE            = 41
DEVICE_NOTIFICATION                     = 60
LIGHT_COLOR_COMMAND                     = 110
LIGHT_COLOR_RESULT                      = 111
PLAY_BEEP_COMMAND                       = 112
PLAY_BEEP_RESULT                        = 113
STOP_SOUND_COMMAND                      = 114
STOP_SOUND_RESULT                       = 115
MOTOR_RESET_RELATIVE_POSITION_COMMAND   = 120
MOTOR_RESET_RELATIVE_POSITION_RESULT    = 121
MOTOR_RUN_COMMAND                       = 122
MOTOR_RUN_RESULT                        = 123
MOTOR_RUN_FOR_DEGREES_COMMAND           = 124
MOTOR_RUN_FOR_DEGREES_RESULT            = 125
MOTOR_RUN_FOR_TIME_COMMAND              = 126
MOTOR_RUN_FOR_TIME_RESULT               = 127
MOTOR_STOP_COMMAND                      = 138
MOTOR_STOP_RESULT                       = 139
MOTOR_SET_SPEED_COMMAND                 = 140
MOTOR_SET_SPEED_RESULT                  = 141
MOTOR_SET_END_STATE_COMMAND             = 142
MOTOR_SET_END_STATE_RESULT              = 143
MOTOR_SET_ACCELERATION_COMMAND          = 144
MOTOR_SET_ACCELERATION_RESULT           = 145
MOVEMENT_MOVE_COMMAND                   = 150
MOVEMENT_MOVE_RESULT                    = 151
MOVEMENT_MOVE_FOR_TIME_COMMAND          = 152
MOVEMENT_MOVE_FOR_TIME_RESULT           = 153
MOVEMENT_MOVE_FOR_DEGREES_COMMAND       = 154
MOVEMENT_MOVE_FOR_DEGREES_RESULT        = 155
MOVEMENT_MOVE_TANK_COMMAND              = 156
MOVEMENT_MOVE_TANK_RESULT               = 157
MOVEMENT_MOVE_TANK_FOR_DEGREES_COMMAND  = 158
MOVEMENT_MOVE_TANK_FOR_DEGREES_RESULT   = 159
MOVEMENT_TURN_FOR_DEGREES_COMMAND       = 160
MOVEMENT_TURN_FOR_DEGREES_RESULT        = 161
MOVEMENT_STOP_COMMAND                   = 168
MOVEMENT_STOP_RESULT                    = 169
MOVEMENT_SET_SPEED_COMMAND              = 170
MOVEMENT_SET_SPEED_RESULT               = 171
MOVEMENT_SET_END_STATE_COMMAND          = 172
MOVEMENT_SET_END_STATE_RESULT           = 173
MOVEMENT_SET_ACCELERATION_COMMAND       = 174
MOVEMENT_SET_ACCELERATION_RESULT        = 175
MOVEMENT_SET_TURN_STEERING_COMMAND      = 176
MOVEMENT_SET_TURN_STEERING_RESULT       = 177
IMU_SET_YAW_FACE_COMMAND                = 190
IMU_SET_YAW_FACE_RESULT                 = 191
IMU_RESET_YAW_AXIS_COMMAND              = 192
IMU_RESET_YAW_AXIS_RESULT               = 193

# Notification sub-type IDs
INFO_DEVICE_NOTIFICATION    = 0
IMU_DEVICE_NOTIFICATION     = 1
CARD_NOTIFICATION           = 3
BUTTON_STATE_NOTIFICATION   = 4
MOTOR_NOTIFICATION          = 10
COLOR_SENSOR_NOTIFICATION   = 12
CONTROLLER_NOTIFICATION     = 15
IMU_GESTURE_NOTIFICATION    = 16

# ---------------------------------------------------------------------------
# App-facing LEGO Color constants  (from color_map.py — these match the docs)
# These are what you use in your code, e.g. LEGO_COLOR_GREEN = 5
# The firmware uses different numbers internally; translation is handled below.
# ---------------------------------------------------------------------------
LEGO_COLOR_NOCOLOR  = 0
LEGO_COLOR_RED      = 1
LEGO_COLOR_YELLOW   = 2
LEGO_COLOR_BLUE     = 3
LEGO_COLOR_TEAL     = 4
LEGO_COLOR_GREEN    = 5
LEGO_COLOR_PURPLE   = 6
LEGO_COLOR_WHITE    = 7
LEGO_COLOR_MAGENTA  = 8
LEGO_COLOR_ORANGE   = 9
LEGO_COLOR_AZURE    = 10

# ---------------------------------------------------------------------------
# Firmware color values (used in BLE manufacturer data for card scanning)
# These differ from the app-facing values above.
# ---------------------------------------------------------------------------
_FW_COLOR_NONE      = -1
_FW_COLOR_BLACK     = 0
_FW_COLOR_MAGENTA   = 1
_FW_COLOR_PURPLE    = 2
_FW_COLOR_BLUE      = 3
_FW_COLOR_AZURE     = 4
_FW_COLOR_TURQUOISE = 5
_FW_COLOR_GREEN     = 6
_FW_COLOR_YELLOW    = 7
_FW_COLOR_ORANGE    = 8
_FW_COLOR_RED       = 9
_FW_COLOR_WHITE     = 10

# Firmware → App color translation (used when parsing color sensor notifications
# and manufacturer data card_color)
_FW_TO_APP = {
    _FW_COLOR_NONE:      LEGO_COLOR_NOCOLOR,
    _FW_COLOR_BLACK:     LEGO_COLOR_NOCOLOR,
    _FW_COLOR_MAGENTA:   LEGO_COLOR_MAGENTA,
    _FW_COLOR_PURPLE:    LEGO_COLOR_PURPLE,
    _FW_COLOR_BLUE:      LEGO_COLOR_BLUE,
    _FW_COLOR_AZURE:     LEGO_COLOR_AZURE,
    _FW_COLOR_TURQUOISE: LEGO_COLOR_TEAL,
    _FW_COLOR_GREEN:     LEGO_COLOR_GREEN,
    _FW_COLOR_YELLOW:    LEGO_COLOR_YELLOW,
    _FW_COLOR_ORANGE:    LEGO_COLOR_ORANGE,
    _FW_COLOR_RED:       LEGO_COLOR_RED,
    _FW_COLOR_WHITE:     LEGO_COLOR_WHITE,
}

# App → Firmware color translation (used when sending light_color commands)
_APP_TO_FW = {
    LEGO_COLOR_NOCOLOR:  _FW_COLOR_NONE,
    LEGO_COLOR_RED:      _FW_COLOR_RED,
    LEGO_COLOR_YELLOW:   _FW_COLOR_YELLOW,
    LEGO_COLOR_BLUE:     _FW_COLOR_BLUE,
    LEGO_COLOR_TEAL:     _FW_COLOR_TURQUOISE,
    LEGO_COLOR_GREEN:    _FW_COLOR_GREEN,
    LEGO_COLOR_PURPLE:   _FW_COLOR_PURPLE,
    LEGO_COLOR_WHITE:    _FW_COLOR_WHITE,
    LEGO_COLOR_MAGENTA:  _FW_COLOR_MAGENTA,
    LEGO_COLOR_ORANGE:   _FW_COLOR_ORANGE,
    LEGO_COLOR_AZURE:    _FW_COLOR_AZURE,
}

def fw_to_app_color(fw_color):
    return _FW_TO_APP.get(fw_color, LEGO_COLOR_NOCOLOR)

def app_to_fw_color(app_color):
    return _APP_TO_FW.get(app_color, _FW_COLOR_NONE)

# ---------------------------------------------------------------------------
# Motor constants
# ---------------------------------------------------------------------------
# Motor Sides (Double Motor) — used as motor= argument in motor_* functions
MOTOR_LEFT  = 0   # = MOTOR_BITS_LEFT  - 1
MOTOR_RIGHT = 1   # = MOTOR_BITS_RIGHT - 1
MOTOR_BOTH  = 2   # = MOTOR_BITS_BOTH  - 1

# Motor Bits — used in MotorNotification.motorBitMask
MOTOR_BITS_LEFT  = 1
MOTOR_BITS_RIGHT = 2
MOTOR_BITS_BOTH  = 3

def motor_side_to_bitmask(motor_side):
    """Convert MOTOR_LEFT/RIGHT/BOTH (0/1/2) to bitmask (1/2/3)."""
    if motor_side == MOTOR_BOTH:
        return MOTOR_BITS_BOTH
    return 1 << motor_side  # 0→1, 1→2

MOTOR_MOVE_DIRECTION_CLOCKWISE        = 0
MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE = 1
MOTOR_MOVE_DIRECTION_SHORTEST         = 2
MOTOR_MOVE_DIRECTION_LONGEST          = 3

MOTOR_END_STATE_DEFAULT     = -1
MOTOR_END_STATE_COAST       = 0
MOTOR_END_STATE_BRAKE       = 1
MOTOR_END_STATE_HOLD        = 2
MOTOR_END_STATE_CONTINUE    = 3
MOTOR_END_STATE_SMART_COAST = 4
MOTOR_END_STATE_SMART_BRAKE = 5

# Motor State
MOTOR_STATE_READY               = 0
MOTOR_STATE_RUNNING             = 1
MOTOR_STATE_STALLED             = 2
MOTOR_STATE_CMD_ABORTED         = 3
MOTOR_STATE_REGULATION_ERROR    = 4
MOTOR_STATE_MOTOR_DISCONNECTED  = 5
MOTOR_STATE_HOLDING             = 6
MOTOR_STATE_DC_RUNNING          = 7
MOTOR_STATE_NOT_ALLOWED_TO_RUN  = 8

# ---------------------------------------------------------------------------
# Movement constants (Double Motor)
# ---------------------------------------------------------------------------
MOVEMENT_DIRECTION_FORWARD  = 0
MOVEMENT_DIRECTION_BACKWARD = 1
MOVEMENT_DIRECTION_LEFT     = 2
MOVEMENT_DIRECTION_RIGHT    = 3

MOVEMENT_MOVE_DIRECTION_FORWARD  = 0
MOVEMENT_MOVE_DIRECTION_BACKWARD = 1

MOVEMENT_TURN_DIRECTION_LEFT  = 2
MOVEMENT_TURN_DIRECTION_RIGHT = 3

# ---------------------------------------------------------------------------
# Other constants
# ---------------------------------------------------------------------------
LIGHT_PATTERN_SOLID        = 0
LIGHT_PATTERN_BREATHE      = 1
LIGHT_PATTERN_PULSE        = 2
LIGHT_PATTERN_SHORT_BLINK  = 3
LIGHT_PATTERN_LONG_BLINK   = 4
LIGHT_PATTERN_DOUBLE_BLINK = 5

SOUND_PATTERN_BEEP_SINGLE         = 0
SOUND_PATTERN_BEEP_DOUBLE         = 1
SOUND_PATTERN_BEEP_TRIPLE         = 2
SOUND_PATTERN_BEEP_UP_MIDDLE_DOWN = 3

BUTTON_STATE_RELEASED = 0
BUTTON_STATE_PRESSED  = 1

PROGRAM_ACTION_START = 0
PROGRAM_ACTION_STOP  = 1

DEVICE_FACE_TOP    = 0
DEVICE_FACE_FRONT  = 1
DEVICE_FACE_RIGHT  = 2
DEVICE_FACE_BOTTOM = 3
DEVICE_FACE_BACK   = 4
DEVICE_FACE_LEFT   = 5

PRODUCT_GROUP_DEVICE_SINGLE_MOTOR = 512
PRODUCT_GROUP_DEVICE_DOUBLE_MOTOR = 513
PRODUCT_GROUP_DEVICE_COLOR_SENSOR = 514
PRODUCT_GROUP_DEVICE_CONTROLLER   = 515

# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------
def _msg(type_id, fmt="", *values):
    header = struct.pack("<B", type_id)
    if fmt:
        return header + struct.pack(fmt, *values)
    return header


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------

def info_request():
    return _msg(INFO_REQUEST)

def program_flow_notification(action=PROGRAM_ACTION_START):
    return _msg(PROGRAM_FLOW_NOTIFICATION, "<B", action)

def device_notification_request(delay_ms=100):
    return _msg(DEVICE_NOTIFICATION_REQUEST, "<H", delay_ms)

# Light / Sound
def light_color(app_color, pattern=LIGHT_PATTERN_SOLID, intensity=100):
    """app_color uses LEGO_COLOR_* app constants; translated to firmware internally."""
    fw_color = app_to_fw_color(app_color)
    return _msg(LIGHT_COLOR_COMMAND, "<bBB", fw_color, pattern, int(intensity))

def play_beep(pattern=SOUND_PATTERN_BEEP_SINGLE, frequency=440, repetitions=1):
    # Firmware counts repeats-after-first, so subtract 1 (matches PC library)
    return _msg(PLAY_BEEP_COMMAND, "<BHB", pattern, int(frequency), max(0, repetitions - 1))

def stop_sound():
    return _msg(STOP_SOUND_COMMAND)

# Individual motor — accepts MOTOR_LEFT/RIGHT/BOTH (0/1/2), converts to bitmask
def motor_set_speed(motor, speed_percent):
    mask = motor_side_to_bitmask(motor)
    return _msg(MOTOR_SET_SPEED_COMMAND, "<Bb", mask, int(speed_percent))

def motor_set_end_state(motor, end_state):
    mask = motor_side_to_bitmask(motor)
    return _msg(MOTOR_SET_END_STATE_COMMAND, "<BB", mask, end_state)

def motor_run(motor, direction=MOTOR_MOVE_DIRECTION_CLOCKWISE):
    mask = motor_side_to_bitmask(motor)
    return _msg(MOTOR_RUN_COMMAND, "<BB", mask, direction)

def motor_run_for_time(motor, time_ms, direction=MOTOR_MOVE_DIRECTION_CLOCKWISE):
    mask = motor_side_to_bitmask(motor)
    return _msg(MOTOR_RUN_FOR_TIME_COMMAND, "<BLB", mask, int(time_ms), direction)

def motor_run_for_degrees(motor, degrees, direction=MOTOR_MOVE_DIRECTION_CLOCKWISE):
    mask = motor_side_to_bitmask(motor)
    return _msg(MOTOR_RUN_FOR_DEGREES_COMMAND, "<BlB", mask, int(degrees), direction)

def motor_stop(motor=MOTOR_BOTH, end_state=MOTOR_END_STATE_BRAKE):
    mask = motor_side_to_bitmask(motor)
    return _msg(MOTOR_STOP_COMMAND, "<BB", mask, end_state & 0xFF)

def motor_reset_relative_position(motor=MOTOR_BOTH, position=0):
    mask = motor_side_to_bitmask(motor)
    return _msg(MOTOR_RESET_RELATIVE_POSITION_COMMAND, "<Bl", mask, int(position))

# Double Motor movement
def movement_move(direction=MOVEMENT_DIRECTION_FORWARD):
    return _msg(MOVEMENT_MOVE_COMMAND, "<B", direction)

def movement_move_for_time(time_ms, direction=MOVEMENT_DIRECTION_FORWARD):
    return _msg(MOVEMENT_MOVE_FOR_TIME_COMMAND, "<LB", int(time_ms), direction)

def movement_move_for_degrees(degrees, direction=MOVEMENT_MOVE_DIRECTION_FORWARD):
    return _msg(MOVEMENT_MOVE_FOR_DEGREES_COMMAND, "<lB", int(degrees), direction)

def movement_move_tank(speed_left, speed_right):
    return _msg(MOVEMENT_MOVE_TANK_COMMAND, "<bb", int(speed_left), int(speed_right))

def movement_move_tank_for_degrees(degrees, speed_left, speed_right):
    return _msg(MOVEMENT_MOVE_TANK_FOR_DEGREES_COMMAND, "<lbb",
                int(degrees), int(speed_left), int(speed_right))

def movement_turn_for_degrees(degrees, direction=MOVEMENT_TURN_DIRECTION_LEFT):
    return _msg(MOVEMENT_TURN_FOR_DEGREES_COMMAND, "<lB", int(degrees), direction)

def movement_stop():
    return _msg(MOVEMENT_STOP_COMMAND)

def movement_set_speed(speed):
    return _msg(MOVEMENT_SET_SPEED_COMMAND, "<b", int(speed))

def movement_set_end_state(end_state):
    return _msg(MOVEMENT_SET_END_STATE_COMMAND, "<B", end_state)

def movement_set_acceleration(acceleration, deceleration):
    return _msg(MOVEMENT_SET_ACCELERATION_COMMAND, "<BB", int(acceleration), int(deceleration))

def movement_set_turn_steering(steering):
    return _msg(MOVEMENT_SET_TURN_STEERING_COMMAND, "<B", int(steering))


# ---------------------------------------------------------------------------
# Response / notification parsers
# ---------------------------------------------------------------------------

def parse_response(data):
    if not data or len(data) < 1:
        return None
    type_id = data[0]
    payload = data[1:]
    try:
        if type_id == INFO_RESPONSE:
            (rpc_maj, rpc_min, rpc_build,
             fw_maj, fw_min, fw_build,
             bl_maj, bl_min, bl_build,
             max_pkt, product_id) = struct.unpack_from("<BBHBBHBBHHH", payload)
            return {
                "type": "InfoResponse",
                "rpc_version": (rpc_maj, rpc_min, rpc_build),
                "firmware": (fw_maj, fw_min, fw_build),
                "max_packet_size": max_pkt,
                "product_id": product_id,
            }
        elif type_id == DEVICE_NOTIFICATION:
            (length,) = struct.unpack_from("<H", payload)
            device_data = payload[2: 2 + length]
            return {
                "type": "DeviceNotification",
                "notifications": _parse_sub_notifications(device_data, length),
            }
        else:
            status = payload[0] if payload else -1
            return {"type": type_id, "status": status}
    except Exception as e:
        return {"type": "ParseError", "error": str(e)}


def _parse_sub_notifications(data, total_length):
    notifications = []
    offset    = 0
    remaining = total_length

    _sizes = {
        INFO_DEVICE_NOTIFICATION:  struct.calcsize("<BB"),
        IMU_DEVICE_NOTIFICATION:   struct.calcsize("<BBhhhhhhhhh"),
        CARD_NOTIFICATION:         struct.calcsize("<bH"),
        BUTTON_STATE_NOTIFICATION: struct.calcsize("<B"),
        MOTOR_NOTIFICATION:        struct.calcsize("<BBHhblb"),
        COLOR_SENSOR_NOTIFICATION: struct.calcsize("<bBHHHHBB"),
        CONTROLLER_NOTIFICATION:   struct.calcsize("<bbhh"),
        IMU_GESTURE_NOTIFICATION:  struct.calcsize("<b"),
    }

    while remaining > 0 and offset < len(data):
        sub_type  = data[offset]
        offset   += 1
        remaining -= 1
        sz = _sizes.get(sub_type)
        if sz is None or remaining < sz:
            break
        chunk = data[offset: offset + sz]

        try:
            if sub_type == INFO_DEVICE_NOTIFICATION:
                (battery, usb) = struct.unpack_from("<BB", chunk)
                notifications.append({
                    "type": "InfoDeviceNotification",
                    "battery_level": battery, "usb_power": usb,
                })
            elif sub_type == IMU_DEVICE_NOTIFICATION:
                (orientation, yaw_face,
                 yaw, pitch, roll,
                 ax, ay, az, gx, gy, gz) = struct.unpack_from("<BBhhhhhhhhh", chunk)
                notifications.append({
                    "type": "ImuDeviceNotification",
                    "orientation": orientation, "yaw_face": yaw_face,
                    "yaw": yaw, "pitch": pitch, "roll": roll,
                    "accel": (ax, ay, az), "gyro": (gx, gy, gz),
                })
            elif sub_type == CARD_NOTIFICATION:
                (fw_color, serial) = struct.unpack_from("<bH", chunk)
                notifications.append({
                    "type": "CardNotification",
                    "color": fw_to_app_color(fw_color), "serial": serial,
                })
            elif sub_type == BUTTON_STATE_NOTIFICATION:
                (state,) = struct.unpack_from("<B", chunk)
                notifications.append({
                    "type": "ButtonStateNotification",
                    "state": state, "pressed": state == BUTTON_STATE_PRESSED,
                })
            elif sub_type == MOTOR_NOTIFICATION:
                (mask, mstate, abs_pos, power, speed, pos, gesture) = struct.unpack_from("<BBHhblb", chunk)
                notifications.append({
                    "type": "MotorNotification",
                    "motorBitMask": mask, "motorState": mstate,
                    "absolutePos": abs_pos,
                    "power": power, "speed": speed, "position": pos,
                    "gesture": gesture,
                })
            elif sub_type == COLOR_SENSOR_NOTIFICATION:
                (fw_color, reflection, raw_r, raw_g, raw_b, hue, sat, val) = struct.unpack_from("<bBHHHHBB", chunk)
                notifications.append({
                    "type": "ColorSensorNotification",
                    # color translated to app-facing value, matching PC library
                    "color": fw_to_app_color(fw_color),
                    "reflection": reflection,
                    "rawRed": raw_r, "rawGreen": raw_g, "rawBlue": raw_b,
                    "hue": hue, "saturation": sat, "value": val,
                })
            elif sub_type == CONTROLLER_NOTIFICATION:
                (lp, rp, la, ra) = struct.unpack_from("<bbhh", chunk)
                notifications.append({
                    "type": "ControllerNotification",
                    "leftPercent": lp, "rightPercent": rp,
                    "leftAngle": la, "rightAngle": ra,
                })
            elif sub_type == IMU_GESTURE_NOTIFICATION:
                (gesture,) = struct.unpack_from("<b", chunk)
                notifications.append({"type": "ImuGestureNotification", "gesture": gesture})
        except Exception as e:
            notifications.append({"type": "SubParseError", "sub_type": sub_type, "error": str(e)})

        offset    += sz
        remaining -= sz

    return notifications
