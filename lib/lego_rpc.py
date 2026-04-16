"""
lego_rpc.py - LEGO Education RPC message serialization for MicroPython (ESP32-C6)

Ported from rpc_message.py. Covers motors, movement (Double Motor),
light, sound, and all notification types.
"""

import struct

# ---------------------------------------------------------------------------
# Message type IDs
# ---------------------------------------------------------------------------
INFO_REQUEST                            = 1
INFO_RESPONSE                           = 2
DEVICE_NOTIFICATION_REQUEST             = 13
DEVICE_NOTIFICATION_RESPONSE            = 14
DEVICE_NOTIFICATION                     = 15
LIGHT_COLOR_COMMAND                     = 50
LIGHT_COLOR_RESULT                      = 51
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

# Notification sub-type IDs (inside DeviceNotification payload)
INFO_DEVICE_NOTIFICATION    = 0
IMU_DEVICE_NOTIFICATION     = 1
CARD_NOTIFICATION           = 3
BUTTON_STATE_NOTIFICATION   = 4
MOTOR_NOTIFICATION          = 10
COLOR_SENSOR_NOTIFICATION   = 12
CONTROLLER_NOTIFICATION     = 15
IMU_GESTURE_NOTIFICATION    = 16

# ---------------------------------------------------------------------------
# Enum constants
# ---------------------------------------------------------------------------
MOTOR_BITS_LEFT  = 1
MOTOR_BITS_RIGHT = 2
MOTOR_BITS_BOTH  = 3

MOTOR_MOVE_DIRECTION_CLOCKWISE        = 0
MOTOR_MOVE_DIRECTION_COUNTERCLOCKWISE = 1
MOTOR_MOVE_DIRECTION_SHORTEST         = 2
MOTOR_MOVE_DIRECTION_LONGEST          = 3

MOTOR_END_STATE_COAST       = 0
MOTOR_END_STATE_BRAKE       = 1
MOTOR_END_STATE_HOLD        = 2
MOTOR_END_STATE_CONTINUE    = 3
MOTOR_END_STATE_SMART_COAST = 4
MOTOR_END_STATE_SMART_BRAKE = 5

MOVEMENT_DIRECTION_FORWARD  = 0
MOVEMENT_DIRECTION_BACKWARD = 1
MOVEMENT_DIRECTION_LEFT     = 2
MOVEMENT_DIRECTION_RIGHT    = 3

MOVEMENT_MOVE_DIRECTION_FORWARD  = 0
MOVEMENT_MOVE_DIRECTION_BACKWARD = 1

MOVEMENT_TURN_DIRECTION_LEFT  = 2
MOVEMENT_TURN_DIRECTION_RIGHT = 3

# Firmware color values (used for card scanning and light commands)
LEGO_COLOR_NONE      = -1
LEGO_COLOR_BLACK     = 0
LEGO_COLOR_MAGENTA   = 1
LEGO_COLOR_PURPLE    = 2
LEGO_COLOR_BLUE      = 3
LEGO_COLOR_AZURE     = 4
LEGO_COLOR_TURQUOISE = 5
LEGO_COLOR_GREEN     = 6
LEGO_COLOR_YELLOW    = 7
LEGO_COLOR_ORANGE    = 8
LEGO_COLOR_RED       = 9
LEGO_COLOR_WHITE     = 10

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

def device_notification_request(delay_ms=100):
    return _msg(DEVICE_NOTIFICATION_REQUEST, "<H", delay_ms)

# Light / Sound
def light_color(color, pattern=LIGHT_PATTERN_SOLID, intensity=100):
    return _msg(LIGHT_COLOR_COMMAND, "<bBB", int(color), pattern, int(intensity))

def play_beep(pattern=SOUND_PATTERN_BEEP_SINGLE, frequency=440, repetitions=1):
    return _msg(PLAY_BEEP_COMMAND, "<BHB", pattern, int(frequency), int(repetitions))

def stop_sound():
    return _msg(STOP_SOUND_COMMAND)

# Individual motor
def motor_set_speed(motor_bitmask, speed_percent):
    return _msg(MOTOR_SET_SPEED_COMMAND, "<Bb", motor_bitmask, int(speed_percent))

def motor_set_end_state(motor_bitmask, end_state):
    return _msg(MOTOR_SET_END_STATE_COMMAND, "<BB", motor_bitmask, end_state)

def motor_run(motor_bitmask, direction=MOTOR_MOVE_DIRECTION_CLOCKWISE):
    return _msg(MOTOR_RUN_COMMAND, "<BB", motor_bitmask, direction)

def motor_run_for_time(motor_bitmask, time_ms, direction=MOTOR_MOVE_DIRECTION_CLOCKWISE):
    return _msg(MOTOR_RUN_FOR_TIME_COMMAND, "<BLB", motor_bitmask, int(time_ms), direction)

def motor_run_for_degrees(motor_bitmask, degrees, direction=MOTOR_MOVE_DIRECTION_CLOCKWISE):
    return _msg(MOTOR_RUN_FOR_DEGREES_COMMAND, "<BlB", motor_bitmask, int(degrees), direction)

def motor_stop(motor_bitmask, end_state=MOTOR_END_STATE_BRAKE):
    return _msg(MOTOR_STOP_COMMAND, "<BB", motor_bitmask, end_state)

def motor_reset_relative_position(motor_bitmask, position=0):
    return _msg(MOTOR_RESET_RELATIVE_POSITION_COMMAND, "<Bl", motor_bitmask, int(position))

# Double Motor movement
def movement_move(direction=MOVEMENT_DIRECTION_FORWARD):
    return _msg(MOVEMENT_MOVE_COMMAND, "<B", direction)

def movement_move_for_time(time_ms, direction=MOVEMENT_DIRECTION_FORWARD):
    """Format: <LB — uint32 time_ms, uint8 direction"""
    return _msg(MOVEMENT_MOVE_FOR_TIME_COMMAND, "<LB", int(time_ms), direction)

def movement_move_for_degrees(degrees, direction=MOVEMENT_MOVE_DIRECTION_FORWARD):
    """Format: <lB — int32 degrees, uint8 direction"""
    return _msg(MOVEMENT_MOVE_FOR_DEGREES_COMMAND, "<lB", int(degrees), direction)

def movement_move_tank(speed_left, speed_right):
    """Format: <bb — int8 left, int8 right"""
    return _msg(MOVEMENT_MOVE_TANK_COMMAND, "<bb", int(speed_left), int(speed_right))

def movement_move_tank_for_degrees(degrees, speed_left, speed_right):
    """Format: <lbb"""
    return _msg(MOVEMENT_MOVE_TANK_FOR_DEGREES_COMMAND, "<lbb",
                int(degrees), int(speed_left), int(speed_right))

def movement_turn_for_degrees(degrees, direction=MOVEMENT_TURN_DIRECTION_LEFT):
    """Format: <lB — int32 degrees, uint8 direction"""
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
    """Parse raw bytes from the GATT notify characteristic into a dict."""
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

        # All other results carry just a status byte
        else:
            status = payload[0] if payload else -1
            return {"type": type_id, "status": status}

    except Exception as e:
        return {"type": "ParseError", "error": str(e)}


def _parse_sub_notifications(data, total_length):
    notifications = []
    offset = 0
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
        sub_type = data[offset]
        offset += 1
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
                (color, serial) = struct.unpack_from("<bH", chunk)
                notifications.append({
                    "type": "CardNotification",
                    "color": color, "serial": serial,
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
                    "motor_mask": mask, "motor_state": mstate,
                    "absolute_position": abs_pos,
                    "power": power, "speed": speed, "position": pos,
                    "gesture": gesture,
                })
            elif sub_type == COLOR_SENSOR_NOTIFICATION:
                (color, reflection, raw_r, raw_g, raw_b, hue, sat, val) = struct.unpack_from("<bBHHHHBB", chunk)
                notifications.append({
                    "type": "ColorSensorNotification",
                    "color": color, "reflection": reflection,
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

        offset += sz
        remaining -= sz

    return notifications