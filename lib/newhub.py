# newhub.py  –  LEGO wireless protocol layer (multi-connection capable)

from bledevice import BLEDevice
import struct
import time

_shared_ble = None   # module-level shared BLEDevice instance

def get_shared_ble():
    global _shared_ble
    if _shared_ble is None:
        _shared_ble = BLEDevice()
    return _shared_ble


class Hub:
    def __init__(self, ble_device=None, slot='default'):
        """
        ble_device – pass a shared BLEDevice to use multi-connection mode.
                     If None, a new BLEDevice is created (single-connection mode).
        slot       – name for this hub's BLE connection slot.
        """
        self.myble = ble_device if ble_device is not None else BLEDevice()
        self.slot  = slot
        self.info  = None
        self.data  = {}

        self.color_lut = {
            255:'NONE', 0:'BLACK', 1:'MAGENTA', 2:'PURPLE',
            3:'BLUE',   4:'AZURE', 5:'TURQUOISE',6:'GREEN',
            7:'YELLOW', 8:'ORANGE',9:'RED',      10:'WHITE',
        }

        self.notify = {
             0: (self.infohub,    1),
             1: (self.imuhub,    20),
             3: (self.taghub,     3),
             4: (self.btnstate,   1),
            10: (self.motor,     12),
            12: (self.color,     12),
            13: (self.joystick,   6),
            14: (self.imugest,    1),
            15: (self.controller, 6),
            16: (self.skip,       1),
        }

    # ── connection helpers ───────────────────────────────────────────────────
    def set_callback(self, cb):
        self.myble.set_callback(self.slot, cb)

    def connect(self, Name='MOT'):
        self.myble.scan(slot=self.slot, name=Name)
        while True:
            if self.myble.is_connected(self.slot):
                self.write([0x00])
                break
            time.sleep(0.1)

    def disconnect(self):
        self.myble.disconnect(self.slot)

    def write(self, data):
        self.myble.write(self.slot, data)

    def is_connected(self):
        return self.myble.is_connected(self.slot)

    # ── struct helpers ───────────────────────────────────────────────────────
    def u16(self, d): return struct.unpack("<H", bytes(d))[0]
    def i16(self, d): return struct.unpack("<h", bytes(d))[0]
    def i32(self, d): return struct.unpack("<i", bytes(d))[0]

    # ── command helpers ──────────────────────────────────────────────────────
    def feed(self, updateTime=200):
        self.write([40, updateTime & 0xFF, updateTime >> 8])

    def beep(self, freq=440, duration=100):
        self.write([112, freq&0xFF, freq>>8,
                    duration&0xFF, (duration>>8)&0xFF,
                    (duration>>16)&0xFF, (duration>>24)&0xFF])

    def motor_speed(self, port=1, speed=100):
        self.write([140, port, speed & 0xFF])

    def motor_stop(self, port=1, end_state=1):
        self.write([138, port, end_state])

    def motor_run(self, port=1, dir=2):
        self.write([122, port, dir])

    def motor_angle(self, port=1, angle=30, direction=2):
        self.write([124, port, angle&0xFF,(angle>>8)&0xFF,
                    (angle>>16)&0xFF,(angle>>24)&0xFF, direction])

    # ── notification decoders ────────────────────────────────────────────────
    def inforesponse(self, data):
        return {
            'RPC':{'major':data[1],'minor':data[2],'build':self.u16(data[3:5])},
            'Firmware':{'major':data[5],'minor':data[6],'build':self.u16(data[7:9])},
            'max_size':{'packet':self.u16(data[9:11]),'message':self.u16(data[11:13]),'chunk':self.u16(data[13:15])},
            'device':self.u16(data[15:17]),
        }

    def infohub(self, data):   return {'battery': data[0]}
    def skip(self, data):      return {}
    def btnstate(self, data):  return {'button': data[0]}

    def imuhub(self, data):
        if len(data) < 20: return {}
        return {'orientation':data[0],'yawFace':data[1],
                'yaw':self.i16(data[2:4]),'pitch':self.i16(data[4:6]),
                'roll':self.i16(data[6:8]),
                'aX':self.i16(data[8:10]),'aY':self.i16(data[10:12]),
                'aZ':self.i16(data[12:14]),
                'gyroX':self.i16(data[14:16]),'gyroY':self.i16(data[16:18]),
                'gyroZ':self.i16(data[18:20])}

    def taghub(self, data):
        return {'color':self.color_lut.get(data[0]),'tag':self.u16(data[1:3])}

    def motor(self, data):
        m = data[0]
        return {'port{}'.format(m):m,'deviceID{}'.format(m):data[1],
                'absolutePos{}'.format(m):self.i32(data[2:6]) if len(data)>=6 else self.i16(data[2:4]),
                'speed{}'.format(m):data[6],
                'position{}'.format(m):self.i32(data[7:11]),
                'state{}'.format(m):data[11] if len(data)>=12 else None}

    def color(self, data):
        return {'color':data[0],'reflection':data[1],
                'rawRed':self.u16(data[2:4]),'rawGreen':self.u16(data[4:6]),
                'rawBlue':self.u16(data[6:8]),'clear':self.u16(data[8:10]),
                'infrared':self.u16(data[10:12])}

    def joystick(self, data):
        return {'leftStep':data[0],'rightStep':data[1],
                'leftAngle':self.i16(data[2:4]),'rightAngle':self.i16(data[4:6])}

    def controller(self, data):
        return {'leftStep':data[0],'rightStep':data[1],
                'leftAngle':self.i16(data[2:4]),'rightAngle':self.i16(data[4:6])}

    def imugest(self, data):
        lut={255:'NO_GESTURE',0:'TAPPED',1:'DOUBLE_TAPPED',2:'COLLISION',3:'SHAKE',4:'FREEFALL'}
        return {'imu_gesture':lut.get(data[0])}

    def motorgest(self, data):
        lut={255:'NO_GESTURE',0:'STOPPED',1:'SLOW_CW',2:'FAST_CW',3:'SLOW_CCW',4:'FAST_CCW',5:'WIGGLED'}
        return {'motor_gesture':lut.get(data[0])}

    # ── packet parser ────────────────────────────────────────────────────────
    def parse(self, data):
        if len(data) < 4: return None
        notification = data[0]
        length = self.u16(data[1:3])
        if len(data) < length + 3: return None

        if notification == 1:
            self.info = self.inforesponse(data)
            return self.info

        if notification == 60:
            if not self.info: return None
            reply = {}
            d = data[3:]
            while d:
                dt = d[0]
                if dt in self.notify:
                    handler, plen = self.notify[dt]
                    if len(d) < plen + 1: break
                    payload = handler(d[1:plen+1])
                    if isinstance(payload, dict) and payload:
                        reply.update(payload)
                    d = d[plen+1:]
                else:
                    break
            return reply if reply else None
        return None
