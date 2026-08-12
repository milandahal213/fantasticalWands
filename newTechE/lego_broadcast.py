"""
lego_broadcast.py - drive LEGO motors by connectionless BLE BROADCAST.

No GATT, no connection: advertise a controller beacon; every motor listening on
the matching card acts on it (many at once). Beacon layout from SimpleLE's
pico_fake_controller.py; the byte2/byte7 "hash" is a CRC-16 of the card's 7-byte
NFC UID (SimpleLE card_mode/card_hash.py) - the motor stored it when tapped, so
our beacon must carry the SAME hash or the motor ignores it.

    b = Broadcaster()
    b.set_card(uid, serial, color)     # uid from the NFC tap -> computes hash
    b.emit(left_pct, right_pct)        # call ~25 Hz
    b.stop()

Service-data payload (after the 0x16 + FD02 AD header):
  [0] type   [1] color   [2] hashHi   [3-4] serial(le)
  [5] LEFT wheel  [6] RIGHT wheel   [7] hashLo   [8] 0x80   [9-11] counter

Drive is TYPE 0x04 (double-motor drive): byte5/byte6 are per-wheel speeds sent
as a signed byte in -100..100 (0x00 stop, 0x01..0x64 fwd, 0x9c..0xff rev), the
value passed straight through -- matching the working legocast reference.
"""

import bluetooth

_TYPE_TAG = 0x04
_BYTE8 = 0x80
_SVC_UUID16 = 0xFD02
_ADV_US = 100_000
_COUNTER_STEP = 0x00B300


# ---- card hash: CRC-16 (poly 0x0001, reflected in/out) of the 7-byte UID ----
def _refl(b, w):
    r = 0
    for i in range(w):
        if b & (1 << i):
            r |= 1 << (w - 1 - i)
    return r


def card_hash(uid):
    """Return (byte2, byte7) for a 7-byte UID. Matches SimpleLE card_hash.py."""
    crc = 0
    for byte in uid:
        crc ^= _refl(byte, 8) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x0001) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    crc = _refl(crc, 16)
    return (crc >> 8) & 0xFF, crc & 0xFF


def _clamp(p):
    return -100 if p < -100 else 100 if p > 100 else p


def _speed8(pct):
    """Speed -100..100 -> signed byte, value passed straight through (matches
    legocast): 0x00 stop, 0x01..0x64 fwd, 0x9c..0xff rev."""
    return int(round(_clamp(pct))) & 0xFF


def _beacon_raw(color, serial, h2, h7, b5, b6, counter):
    svc = bytes([
        _TYPE_TAG, color, h2,
        serial & 0xFF, (serial >> 8) & 0xFF,
        b5 & 0xFF, b6 & 0xFF, h7, _BYTE8,
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,
    ])
    sd = bytes([0x16, _SVC_UUID16 & 0xFF, (_SVC_UUID16 >> 8) & 0xFF]) + svc
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(sd)]) + sd


def _beacon(color, serial, h2, h7, left_pct, right_pct, counter):
    # byte5 = LEFT wheel, byte6 = RIGHT wheel
    return _beacon_raw(color, serial, h2, h7,
                       _speed8(left_pct), _speed8(right_pct), counter)


class Broadcaster:
    # Defaults = the Purple/1126 card (UID 0413AA7ACC2191 -> hash F3:48), used
    # until a card is tapped. Tap a real card to drive any other motor.
    def __init__(self, color=0x02, serial=1126, h2=0xF3, h7=0x48):
        self.ble = bluetooth.BLE()
        if not self.ble.active():
            self.ble.active(True)
        self.color = color
        self.serial = serial
        self.h2 = h2
        self.h7 = h7
        self.counter = 0

    def set_card(self, uid, serial, color):
        """Point the broadcast at a tapped card: compute its hash from the UID."""
        self.h2, self.h7 = card_hash(uid)
        self.serial = serial
        self.color = color

    def _adv(self, adv):
        self.ble.gap_advertise(None)
        self.ble.gap_advertise(_ADV_US, adv_data=adv, connectable=False)
        self.counter = (self.counter + _COUNTER_STEP) & 0xFFFFFF

    def emit(self, left_pct, right_pct):
        self._adv(_beacon(self.color, self.serial, self.h2, self.h7,
                          left_pct, right_pct, self.counter))

    def emit_raw(self, b5, b6):
        """Broadcast raw per-wheel bytes (b5=left, b6=right), bypassing speed
        scaling -- for calibrating the byte->speed curve."""
        self._adv(_beacon_raw(self.color, self.serial, self.h2, self.h7,
                              b5, b6, self.counter))

    def stop(self):
        try:
            self.ble.gap_advertise(None)
        except Exception:
            pass
