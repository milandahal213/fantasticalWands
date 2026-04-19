# newhub.py  –  LEGO wireless protocol layer
# Works on both SPIKE Prime and ESP32C6.

from bledevice import BLEDevice
import struct
import time


class Hub:
    def __init__(self):
        self.info    = None
        self.device  = None
        self.myble   = BLEDevice()

        self.color_lut = {
            255: 'NONE',  0: 'BLACK',  1: 'MAGENTA',  2: 'PURPLE',
              3: 'BLUE',  4: 'AZURE',  5: 'TURQUOISE', 6: 'GREEN',
              7: 'YELLOW',8: 'ORANGE', 9: 'RED',       10: 'WHITE',
        }

        # notification-type → (handler_fn, payload_bytes)
        # Type 0x10 (16): present in Double Motor packets between IMU and motor
        # records.  1-byte payload, always 0xff.  Meaning unknown – skip it.
        self.notify = {
             0: (self.infohub,     1),
             1: (self.imuhub,     20),
             3: (self.taghub,      3),
             4: (self.btnstate,    1),
            10: (self.motor,      12),   # 12 bytes: Double Motor layout
            12: (self.color,      18),
            13: (self.joystick,    6),
            14: (self.imugest,     1),
            15: (self.controller,  6),   # Controller joystick: leftStep, rightStep, leftAngle(i16), rightAngle(i16)
            16: (self.skip,        1),   # 0x10 – unknown, 1-byte payload, skip
        }

    # ── connection helpers ───────────────────────────────────────────────────
    def callback(self, cb):
        self.myble.callback = cb

    def connect(self, Name='MOT'):
        self.myble.scan(5000, None, Name)
        while True:
            if self.myble.is_connected():
                self.write([0x00])
                break
            time.sleep(0.1)

    def disconnect(self):
        self.myble.disconnect()

    def write(self, data):
        self.myble.write(data)

    # ── struct helpers ───────────────────────────────────────────────────────
    def u16(self, data): return struct.unpack("<H", bytes(data))[0]
    def i16(self, data): return struct.unpack("<h", bytes(data))[0]
    def i32(self, data): return struct.unpack("<i", bytes(data))[0]

    # ── command helpers ──────────────────────────────────────────────────────
    def feed(self, updateTime=50):
        data = [40, updateTime & 0xFF, updateTime >> 8]
        self.write(data)

    def beep(self, freq=440, duration=100):
        data = [112,
                freq     & 0xFF,  freq     >> 8,
                duration & 0xFF, (duration >> 8)  & 0xFF,
                (duration >> 16) & 0xFF, (duration >> 24) & 0xFF]
        self.write(data)

    def motor_speed(self, port=1, speed=100):
        data = [140, port, speed & 0xFF]
        self.write(data)

    def motor_angle(self, port=1, angle=30, direction=2):
        data = [124, port,
                angle & 0xFF, (angle >> 8) & 0xFF,
                (angle >> 16) & 0xFF, (angle >> 24) & 0xFF,
                direction]
        self.write(data)

    def motor_abs_pos(self, port=1, pos=30, direction=2):
        data = [128, port, pos & 0xFF, (pos >> 8) & 0xFF, direction]
        self.write(data)

    def motor_stop(self, port=1, end_state=0):
        data = [138, port, end_state]
        self.write(data)

    def motor_run(self, port=1, dir=2):
        data = [122, port, dir]
        self.write(data)

    # ── notification decoders ────────────────────────────────────────────────
    def inforesponse(self, data):
        return {
            'RPC':      {'major': data[1], 'minor': data[2],
                         'build': self.u16(data[3:5])},
            'Firmware': {'major': data[5],  'minor': data[6],
                         'build': self.u16(data[7:9])},
            'max_size': {'packet':  self.u16(data[9:11]),
                         'message': self.u16(data[11:13]),
                         'chunk':   self.u16(data[13:15])},
            'device':   self.u16(data[15:17]),
        }

    def infohub(self, data):
        return {'battery': data[0]}

    def imuhub(self, data):
        if len(data) < 20:
            return {}
        return {
            'orientation': data[0],  'yawFace': data[1],
            'yaw':   self.i16(data[2:4]),   'pitch': self.i16(data[4:6]),
            'roll':  self.i16(data[6:8]),
            'aX':    self.i16(data[8:10]),  'aY':   self.i16(data[10:12]),
            'aZ':    self.i16(data[12:14]),
            'gyroX': self.i16(data[14:16]), 'gyroY':self.i16(data[16:18]),
            'gyroZ': self.i16(data[18:20]),
        }

    def taghub(self, data):
        c = self.color_lut.get(data[0])
        return {'color': c, 'tag': self.u16(data[1:3])}

    def btnstate(self, data):
        return {'button': data[0]}

    def motor(self, data):
        """Decode a motor sub-record.

        Double Motor layout (12 bytes):
          [0]      port
          [1]      deviceID
          [2:6]    absolutePos  (i32 – 4 bytes)
          [6]      speed
          [7:11]   position     (i32 – 4 bytes)
          [11]     state        (0=ready/coast, 1=running, 0xff=stopped)

        Single Motor layout (11 bytes, same structure but absolutePos is
        i32 with the upper two bytes always 0 for small angles, so i16
        and i32 agree for values < 32767):
          Falls back gracefully – just ignores the missing 12th byte.
        """
        m = data[0]
        abs_pos  = self.i32(data[2:6]) if len(data) >= 6 else self.i16(data[2:4])
        position = self.i32(data[7:11])
        state    = data[11] if len(data) >= 12 else None
        return {
            'port{}'.format(m):        m,
            'deviceID{}'.format(m):    data[1],
            'absolutePos{}'.format(m): abs_pos,
            'speed{}'.format(m):       data[6],
            'position{}'.format(m):    position,
            'state{}'.format(m):       state,
        }

    def skip(self, data):
        """Placeholder for known-but-unneeded sub-record types."""
        return {}

    def color(self, data):
        return {
            'color':      data[0], 'reflection': data[1],
            'rawRed':   self.u16(data[2:4]),   'rawGreen': self.u16(data[4:6]),
            'rawBlue':  self.u16(data[6:8]),   'clear':    self.u16(data[8:10]),
            'infrared': self.u16(data[10:12]), 'hue':      self.u16(data[12:14]),
            'saturation': self.u16(data[14:16]), 'value':  self.u16(data[16:]),
        }

    def joystick(self, data):
        return {
            'leftStep':   data[0],
            'rightStep':  data[1],
            'leftAngle':  self.i16(data[2:4]),
            'rightAngle': self.i16(data[4:6]),
        }

    def imugest(self, data):
        lut = {255:'NO_GESTURE', 0:'TAPPED', 1:'DOUBLE_TAPPED',
               2:'COLLISION',    3:'SHAKE',  4:'FREEFALL'}
        return {'imu_gesture': lut.get(data[0])}

    def motorgest(self, data):
        lut = {255:'NO_GESTURE', 0:'STOPPED',  1:'SLOW_CW',  2:'FAST_CW',
               3:'SLOW_CCW',     4:'FAST_CCW', 5:'WIGGLED'}
        return {'motor_gesture': lut.get(data[0])}

    def controller(self, data):
        return {
            'leftStep':   data[0],
            'rightStep':  data[1],
            'leftAngle':  self.i16(data[2:4]),
            'rightAngle': self.i16(data[4:6]),
        }

    # ── incoming packet parser ───────────────────────────────────────────────
    def parse(self, data):
        if len(data) < 4:
            return None

        notification = data[0]
        length       = self.u16(data[1:3])

        if len(data) < length + 3:
            return None

        if notification == 1:
            self.info = self.inforesponse(data)
            return self.info

        if notification == 60:
            if not self.info:
                return None

            reply = {}
            d     = data[3:]
            while d:
                data_type = d[0]
                if data_type in self.notify:
                    handler, plen = self.notify[data_type]
                    if len(d) < plen + 1:
                        break
                    payload = handler(d[1 : plen + 1])
                    if isinstance(payload, dict) and payload:
                        reply.update(payload)
                    d = d[plen + 1:]
                else:
                    break
            return reply if reply else None

        return None