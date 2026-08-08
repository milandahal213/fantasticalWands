# legocast.py — "advertise mode" for the wand.
#
# Turns the wand into a LEGO group *sender*: it broadcasts a connectionless
# fd02 beacon (the same channel real LEGO controllers/sensors use) so that a
# motor tapped with the same card drives itself from the wand's accelerometer —
# no BLE connection required.
#
# This is the counterpart to the connect-based programming system in
# runloop.py. main.py toggles between the two on a long button press.
#
# Beacon layout (12 bytes of fd02 service data), reverse-engineered:
#   b0 type tag | b1 card colour | b2 hash | b3-4 serial (LE) |
#   b5 left wheel / b6 right wheel (speed) | b7 hash | b8 const |
#   b9-11 rolling counter
# b2/b7 are CRC-16(UID) — the motor validates them, so we compute them from
# the tapped card's NFC UID (card_hash below).

import time

FD02_UUID16   = 0xFD02
DEFAULT_TYPE  = 0x04        # device-type tag we broadcast (byte0)
BYTE8         = 0x80
COUNTER_STEP  = 0x00B300    # bump the rolling counter each packet (anti-stale)
ADV_INTERVAL_US = 100_000
UPDATE_MS     = 80          # accel-read + rebroadcast period
HOLD_MS       = 1500        # button hold to toggle modes


def card_hash(uid):
    """(byte2, byte7) = CRC-16 of the 7-byte NFC UID, poly 0x0001 (x^16+1,
    a 16-bit XOR fold), reflected in/out, init 0, big-endian b2:b7."""
    def refl(b, w):
        r = 0
        for i in range(w):
            if b & (1 << i):
                r |= 1 << (w - 1 - i)
        return r
    crc = 0
    for byte in uid:
        crc ^= refl(byte, 8) << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x0001) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    crc = refl(crc, 16)
    return (crc >> 8) & 0xFF, crc & 0xFF


def build_beacon(type_tag, color, b2, serial, b7, b5, b6, counter):
    """Full advertising payload: Flags AD + Service-Data(0xFD02) AD."""
    svc = bytes([
        type_tag & 0xFF, color & 0xFF, b2 & 0xFF,
        serial & 0xFF, (serial >> 8) & 0xFF,
        b5 & 0xFF, b6 & 0xFF,
        b7 & 0xFF, BYTE8,
        (counter >> 16) & 0xFF, (counter >> 8) & 0xFF, counter & 0xFF,
    ])
    sd = bytes([0x16, FD02_UUID16 & 0xFF, (FD02_UUID16 >> 8) & 0xFF]) + svc
    flags = bytes([0x02, 0x01, 0x06])
    return flags + bytes([len(sd)]) + sd


# ── accelerometer → differential drive ───────────────────────────────
# b5 = LEFT wheel, b6 = RIGHT wheel.
#   x tilt = throttle (forward / reverse)
#   y tilt = steering (left / right)
# Calibration from the capture: rest ~ (x 0, y +0.1), full tilt ~ +/-0.95 g.
# Edit these if your neutral / full-tilt positions differ.
X_REST, X_FULL, X_DEAD = 0.00, 0.95, 0.15      # throttle axis
Y_REST, Y_FULL, Y_DEAD = 0.10, 0.95, 0.25      # steering axis
MAX_SPEED = 100                                 # peak wheel magnitude (tune to motor)

# The two motors are mounted mirror-image, so one must be reversed to make the
# robot drive straight. Flip whichever wheel goes the wrong way.
INVERT_LEFT  = True
INVERT_RIGHT = False


def _norm(a, rest, full, dead):
    """Centre on rest, apply a deadzone, scale to -1..+1."""
    a -= rest
    if -dead < a < dead:
        return 0.0
    return -1.0 if a < -full else 1.0 if a > full else a / full


def _speed_byte(s):
    """Signed wheel speed -> beacon byte.

    ASSUMPTION for device type 0x04: b5/b6 are read as signed 8-bit
    (0x00 stop, 0x01..0x7f forward, 0x80..0xff reverse). If the real curve
    differs (you saw ~0x01 slow -> ~0x90 fastest), tune only this function."""
    s = int(round(s))
    s = -MAX_SPEED if s < -MAX_SPEED else MAX_SPEED if s > MAX_SPEED else s
    return s & 0xFF


def accel_to_sticks(x, y, z):
    """x = throttle, y = steering -> (b5 left, b6 right) via arcade mixing."""
    throttle = _norm(x, X_REST, X_FULL, X_DEAD)     # -1 reverse .. +1 forward
    steer    = _norm(y, Y_REST, Y_FULL, Y_DEAD)     # -1 left    .. +1 right
    left  = throttle + steer                        # turning right speeds L, slows R
    right = throttle - steer
    left  = -1.0 if left  < -1.0 else 1.0 if left  > 1.0 else left
    right = -1.0 if right < -1.0 else 1.0 if right > 1.0 else right
    if INVERT_LEFT:  left  = -left                  # mirror-mounted motor fix
    if INVERT_RIGHT: right = -right
    return _speed_byte(left * MAX_SPEED), _speed_byte(right * MAX_SPEED)


# ── long-press mode button ────────────────────────────────────────────
class ModeButton:
    """Fires once when the button is held >= hold_ms; re-arms on release."""
    def __init__(self, wand, hold_ms=HOLD_MS):
        self.wand = wand
        self.hold_ms = hold_ms
        self._start = None
        self._fired = False

    def check(self):
        if self.wand.button_pressed():
            if self._start is None:
                self._start = time.ticks_ms()
                self._fired = False
            elif (not self._fired and
                  time.ticks_diff(time.ticks_ms(), self._start) >= self.hold_ms):
                self._fired = True
                return True
        else:
            self._start = None
            self._fired = False
        return False


# ── card binding ──────────────────────────────────────────────────────
def bind_card(wand):
    """Wait for a card tap; return (beacon_color, serial, b2, b7, app_color).

    beacon_color is the raw colour byte put into the beacon; app_color is the
    remapped colour used elsewhere (status LEDs, connect-mode pairing). b2/b7
    are the hash computed from the card's NFC UID."""
    from program_cards import read_card_universal_full
    print("advertise mode — tap the card to bind...")
    while True:
        wand.pixels_card_prompt()                    # breathing 'tap card'
        r = read_card_universal_full(wand, timeout_ms=200)
        if r is None:
            time.sleep_ms(20)
            continue
        uid, raw_color, app_color, serial = r
        b2, b7 = card_hash(uid)
        wand.beep(1500, 60)
        wand.pixels_flash_card(app_color, flashes=1)
        print("bound colour={} serial={} uid={} hash={:02x}{:02x}".format(
            app_color, serial, bytes(uid).hex(), b2, b7))
        return raw_color, serial, b2, b7, app_color


# ── the advertise loop ────────────────────────────────────────────────
def advertise_mode(wand, ble, card, modebtn, type_tag=DEFAULT_TYPE):
    """Broadcast an fd02 beacon whose b5/b6 track the accelerometer, until the
    button is long-pressed (then return so main can switch to connect mode)."""
    beacon_color, serial, b2, b7, app_color = card
    counter = 0
    try:
        wand.pixels_card_faint(app_color)            # faint = advertise active
    except Exception:
        pass
    print("ADVERTISE type=0x{:02x} card colour={} serial={}".format(
        type_tag, app_color, serial))

    accel = wand.accel                               # lazy-init the sensor
    while True:
        if modebtn.check():
            ble.advertise_stop()
            return
        try:
            x, y, z = accel.read()
        except Exception:
            x = y = z = 0.0
        b5, b6 = accel_to_sticks(x, y, z)
        ble.advertise(build_beacon(type_tag, beacon_color, b2, serial, b7,
                                   b5, b6, counter))
        counter = (counter + COUNTER_STEP) & 0xFFFFFF
        time.sleep_ms(UPDATE_MS)
