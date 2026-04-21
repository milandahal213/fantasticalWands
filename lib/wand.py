# wand.py — unified driver for the LEGO "Wand" (ESP32C6)
#
# Hardware on the wand:
#   - PN532 NFC reader (I2C, 0x24)   → read LEGO Connection Cards
#   - 5x5 NeoPixel grid on pin 20
#   - Button on pin 0 (active low)
#   - Buzzer on pin 19
#   - LIS2DW12 accelerometer (I2C, 0x19)
#   - OPT3002 light sensor     (I2C, 0x44)
#   - MAX17048 battery gauge   (I2C, 0x36)
#
# Usage:
#   from wand import Wand, CARD_RGB
#   w = Wand()
#   color, serial = w.read_card()              # animated prompt + flash on success

import machine
import neopixel
import time

# ── I2C pins and addresses ───────────────────────────────
I2C_SDA    = 22
I2C_SCL    = 23
PN532_ADDR = 0x24
ACCEL_ADDR = 0x19
BATT_ADDR  = 0x36
LIGHT_ADDR = 0x44

# ── NeoPixel / button / buzzer pins ──────────────────────
PIXEL_PIN  = 20
PIXEL_N    = 25
BUTTON_PIN = 0
BUZZER_PIN = 19

# ── LEGO card colors ─────────────────────────────────────
CARD_BLACK     = 0
CARD_MAGENTA   = 1
CARD_PURPLE    = 2
CARD_BLUE      = 3
CARD_AZURE     = 4
CARD_TURQUOISE = 5
CARD_GREEN     = 6
CARD_YELLOW    = 7
CARD_ORANGE    = 8
CARD_RED       = 9
CARD_WHITE     = 10

CARD_COLOR_NAMES = {
    0:'BLACK', 1:'MAGENTA', 2:'PURPLE', 3:'BLUE', 4:'AZURE',
    5:'TURQUOISE', 6:'GREEN', 7:'YELLOW', 8:'ORANGE', 9:'RED', 10:'WHITE',
}

# The byte stored on the NFC card is NOT the same as the LEGO app color ID.
# This table remaps the raw byte we read off page 5 → the app-aligned color ID.
# Populated from observed cards; unknown bytes fall through unchanged.
_RAW_TO_APP_COLOR = {
    0x01: 8,   # MAGENTA
    0x02: 6,   # PURPLE
    0x04: 2,   # YELLOW
    0x07: 2,   # YELLOW (multi variant)
    0x08: 9,
    0x09: 1,   # RED
}


def _raw_to_app_color(raw_byte):
    """Translate the raw color byte from the card → LEGO app color ID.
    Unknown bytes pass through unchanged (best-effort)."""
    return _RAW_TO_APP_COLOR.get(raw_byte, raw_byte)

# RGB (0..255) values for displaying each card color on the NeoPixels.
CARD_RGB = {
    CARD_BLACK    : (  0,   0,   0),
    CARD_MAGENTA  : (228,  89, 158),
    CARD_PURPLE   : ( 75,  47, 145),
    CARD_BLUE     : (  0, 108, 184),
    CARD_AZURE    : (120, 191, 234),
    CARD_TURQUOISE: ( 32, 201, 151),
    CARD_GREEN    : ( 97, 168,  54),
    CARD_YELLOW   : (255, 212,   0),
    CARD_ORANGE   : (245, 125,  32),
    CARD_RED      : (222,  26,  33),
    CARD_WHITE    : (255, 255, 255),
}

# ── PN532 protocol constants ─────────────────────────────
_TFI_HOST2PN532 = 0xD4
_TFI_PN5322HOST = 0xD5
_CMD_SAMCONFIGURATION    = 0x14
_CMD_INLISTPASSIVETARGET = 0x4A
_CMD_INDATAEXCHANGE      = 0x40
_MIFARE_CMD_READ         = 0x30


def _scale(rgb, brightness):
    return (int(rgb[0] * brightness),
            int(rgb[1] * brightness),
            int(rgb[2] * brightness))


class Wand:
    """Combined driver for all wand hardware."""

    def __init__(self, pixel_brightness=0.25):
        self.i2c = machine.SoftI2C(sda=machine.Pin(I2C_SDA),
                                   scl=machine.Pin(I2C_SCL),
                                   freq=100_000)
        self._seen_on_bus = self.i2c.scan()

        # NeoPixels
        self.np = neopixel.NeoPixel(machine.Pin(PIXEL_PIN), PIXEL_N)
        self.pixel_brightness = pixel_brightness
        self.pixels_clear()

        # Button (active low, internal pull-up)
        self.button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

        # Buzzer (PWM)
        self._buzz = machine.PWM(machine.Pin(BUZZER_PIN), freq=1000, duty=0)

        # PN532 only if on the bus
        self._nfc_ready = False
        if PN532_ADDR in self._seen_on_bus:
            try:
                self._sam_config()
                self._nfc_ready = True
            except Exception as e:
                print("NFC init failed:", e)

        # Boot indicator: faint white center square means 'wand ready,
        # waiting for card'.
        self.pixels_center_square((4, 4, 4))

    # ── NeoPixel helpers ────────────────────────────────
    def pixels_clear(self):
        for i in range(PIXEL_N):
            self.np[i] = (0, 0, 0)
        self.np.write()

    def pixels_fill(self, rgb):
        scaled = _scale(rgb, self.pixel_brightness)
        for i in range(PIXEL_N):
            self.np[i] = scaled
        self.np.write()

    def pixels_fill_card(self, color_id):
        self.pixels_fill(CARD_RGB.get(color_id, (0, 0, 0)))

    def pixels_breathing(self, rgb, period_ms=1600):
        """One frame of a breathing animation. Call in a loop."""
        t = time.ticks_ms() % period_ms
        half = period_ms // 2
        level = t / half if t < half else (period_ms - t) / half
        b = self.pixel_brightness * level
        scaled = _scale(rgb, b)
        for i in range(PIXEL_N):
            self.np[i] = scaled
        self.np.write()

    def pixels_card_prompt(self, color_id=None, period_ms=1600):
        """Breathing 'tap card' animation. Pass a card color or None for rainbow."""
        if color_id is not None:
            self.pixels_breathing(CARD_RGB.get(color_id, (255,255,255)), period_ms)
        else:
            colors = list(CARD_RGB.values())
            idx = (time.ticks_ms() // period_ms) % len(colors)
            self.pixels_breathing(colors[idx], period_ms)

    def pixels_flash_card(self, color_id, flashes=2, on_ms=150, off_ms=120):
        rgb = CARD_RGB.get(color_id, (255, 255, 255))
        for _ in range(flashes):
            self.pixels_fill(rgb)
            time.sleep_ms(on_ms)
            self.pixels_clear()
            time.sleep_ms(off_ms)

    def pixels_center_only(self, rgb=(2, 2, 2)):
        """Light ONLY the center pixel (index 12). Used to show 'card detected,
        connecting…'. Preserves top/bottom status rows."""
        for i in range(5, 20):
            self.np[i] = (0, 0, 0)
        self.np[12] = rgb
        self.refresh_status()

    def pixels_middle_clear(self):
        """Clear only the middle 15 pixels (rows 2-4). Preserves status rows.
        Call this after the BLE connection is made to stop the animation."""
        for i in range(5, 20):
            self.np[i] = (0, 0, 0)
        self.refresh_status()

    # A dim palette for displaying a card color on the center square.
    # Small values keep it gentle on the eyes but visible.
    _FAINT_CARD_RGB = {
        CARD_BLACK    : (0, 0, 0),
        CARD_MAGENTA  : (10,  3,  6),
        CARD_PURPLE   : ( 5,  2, 10),
        CARD_BLUE     : ( 0,  4, 10),
        CARD_AZURE    : ( 4,  8, 10),
        CARD_TURQUOISE: ( 0, 10,  5),
        CARD_GREEN    : ( 3, 10,  2),
        CARD_YELLOW   : (10, 10,  0),
        CARD_ORANGE   : (10,  4,  0),
        CARD_RED      : (10,  0,  0),
        CARD_WHITE    : ( 8,  8,  8),
    }

    def pixels_card_faint(self, color_id):
        """Fill grid with a very faint (<= 2 per channel) version of the
        given card color. Used as a persistent 'connected to <color>'
        indicator that won't be distracting."""
        rgb = self._FAINT_CARD_RGB.get(color_id, (1, 1, 1))
        for i in range(PIXEL_N):
            self.np[i] = rgb
        self.np.write()

    # ══════════════════════════════════════════════════════
    #   Status panel
    # ══════════════════════════════════════════════════════
    #
    # Top row (pixels 0..4)  — one pixel per LEGO device type:
    #     0 = Color Sensor   (pink)
    #     1 = Controller     (pink)
    #     2 = Single Motor   (green)
    #     3 = Double Motor   (green)
    #     4 = reserved
    #   Pixel blinks while "connecting", steady when "connected", off when idle.
    #
    # Bottom row (pixels 20..24) — displays the color of the last-tapped card.
    #
    # Middle rows (pixels 5..19) are free for the spinner / card-read animation.

    # Device slot bookkeeping. Keys: 'color', 'ctrl', 'smotor', 'dmotor'.
    _DEVICE_PIXEL = {'color': 0, 'ctrl': 1, 'smotor': 2, 'dmotor': 3}
    _DEVICE_RGB   = {'color': (6, 0, 3), 'ctrl':   (6, 0, 3),   # pink
                     'smotor':(0, 6, 0), 'dmotor': (0, 6, 0)}   # green

    # 'idle' | 'connecting' | 'connected'
    _device_state = None  # dict: device_key -> state, created on first use
    _card_row_rgb = None  # RGB tuple shown on the bottom row

    def _ensure_state(self):
        if self._device_state is None:
            self._device_state = {k: 'idle' for k in self._DEVICE_PIXEL}

    def set_device_state(self, device, state):
        """Set the status for one device strip pixel.
        device: 'color' | 'ctrl' | 'smotor' | 'dmotor'
        state:  'idle' | 'connecting' | 'connected'
        Call refresh_status() after to redraw."""
        self._ensure_state()
        if device not in self._DEVICE_PIXEL:
            raise ValueError("Unknown device: " + str(device))
        if state not in ('idle', 'connecting', 'connected'):
            raise ValueError("Unknown state: " + str(state))
        self._device_state[device] = state

    def set_card_row(self, color_id):
        """Paint the bottom row (pixels 20..24) with a faint version of the
        given LEGO card color. Call refresh_status() after to redraw.
        Pass None to clear it."""
        if color_id is None:
            self._card_row_rgb = None
        else:
            self._card_row_rgb = self._FAINT_CARD_RGB.get(color_id, (1, 1, 1))

    def refresh_status(self):
        """Redraw the top row (device states) — no blinking, just off/on.
        Preserves the middle and bottom rows."""
        self._ensure_state()

        for device, pixel in self._DEVICE_PIXEL.items():
            st = self._device_state.get(device, 'idle')
            if st == 'connected':
                self.np[pixel] = self._DEVICE_RGB[device]
            else:
                # idle or connecting -> off (only show on successful connect)
                self.np[pixel] = (0, 0, 0)
        # Pixel 4 is reserved/off
        self.np[4] = (0, 0, 0)

        self.np.write()

    # Pixels used for the loading spinner, walked clockwise.
    # Inner ring of the 5x5 grid (3x3 minus center).
    _SPINNER_RING = (6, 7, 8, 13, 18, 17, 16, 11)

    # Middle 3x3 square of the 5x5 grid (inner 3x3 block).
    _CENTER_SQUARE = (6, 7, 8, 11, 12, 13, 16, 17, 18)

    def pixels_center_square(self, rgb=(4, 4, 4)):
        """Light the center 3x3 square in the given color. Preserves the
        top status row."""
        # Clear everything below the top row, then paint the square
        for i in range(5, PIXEL_N):
            self.np[i] = (0, 0, 0)
        for idx in self._CENTER_SQUARE:
            self.np[idx] = rgb
        self.refresh_status()

    # Back-compat aliases
    pixels_bouncer   = pixels_center_square
    pixels_spinner   = pixels_center_square
    pixels_center_only = pixels_center_square

    # ── Button / buzzer ─────────────────────────────────
    def button_pressed(self):
        return self.button.value() == 0

    def beep(self, freq=1000, duration_ms=100):
        self._buzz.freq(freq)
        self._buzz.duty(512)
        time.sleep_ms(duration_ms)
        self._buzz.duty(0)

    def buzzer_silent(self):
        self._buzz.duty(0)

    def play_connect_jingle(self):
        """'tidi-tik-tiiik' — short pulse, short pulse, long high note."""
        self.beep(1200,  60); time.sleep_ms(40)
        self.beep(1600,  60); time.sleep_ms(40)
        self.beep(2200, 180)

    # ── PN532 low level ─────────────────────────────────
    def _wait_ready(self, timeout=1000):
        start = time.ticks_ms()
        while True:
            try:
                if self.i2c.readfrom(PN532_ADDR, 1)[0] == 0x01:
                    return True
            except OSError:
                pass
            if time.ticks_diff(time.ticks_ms(), start) > timeout:
                return False
            time.sleep_ms(10)

    def _write_command(self, cmd, params=b''):
        payload = bytes([_TFI_HOST2PN532, cmd]) + bytes(params)
        length = len(payload)
        lcs = (~length + 1) & 0xFF
        frame = bytearray([0x00, 0x00, 0xFF, length, lcs])
        frame.extend(payload)
        dcs = (~sum(payload) + 1) & 0xFF
        frame.append(dcs)
        frame.append(0x00)
        self.i2c.writeto(PN532_ADDR, frame)

    def _read_ack(self, timeout=500):
        if not self._wait_ready(timeout): raise RuntimeError("ACK timeout")
        self.i2c.readfrom(PN532_ADDR, 7)

    def _read_response(self, timeout=1000):
        if not self._wait_ready(timeout): raise RuntimeError("Response timeout")
        buf = bytes(self.i2c.readfrom(PN532_ADDR, 64))
        offset = -1
        for i in range(len(buf) - 4):
            if buf[i] == 0x00 and buf[i+1] == 0xFF and buf[i+2] != 0x00:
                offset = i; break
        if offset < 0: raise RuntimeError("No frame start")
        frame_len = buf[offset + 2]
        return buf[offset + 4 : offset + 4 + frame_len]

    def _send_command(self, cmd, params=b'', timeout=1000):
        self._write_command(cmd, params)
        time.sleep_ms(5)
        self._read_ack(timeout=timeout)
        resp = self._read_response(timeout=timeout)
        if len(resp) < 2 or resp[0] != _TFI_PN5322HOST or resp[1] != cmd + 1:
            raise RuntimeError("Bad response")
        return resp[2:]

    def _sam_config(self):
        self._send_command(_CMD_SAMCONFIGURATION, b'\x01\x00\x00')

    def _detect_tag(self, timeout=500):
        try:
            resp = self._send_command(_CMD_INLISTPASSIVETARGET, b'\x01\x00', timeout=timeout)
        except RuntimeError:
            return False
        return len(resp) >= 6 and resp[0] != 0

    def _read_page(self, page):
        resp = self._send_command(_CMD_INDATAEXCHANGE,
                                  bytes([0x01, _MIFARE_CMD_READ, page]), timeout=1000)
        if (resp[0] & 0x3F) != 0:
            raise RuntimeError("Read error 0x{:02X}".format(resp[0]))
        return resp[1:5]

    # ── NFC public API ──────────────────────────────────
    _last_card_color = None  # remembers the last tapped card for the square

    def read_card(self, timeout_ms=None, animate=True):
        """Wait for a LEGO Connection Card. Returns (color, serial) or None on timeout.

        animate=True shows the center square: faint white until any card
        has been tapped, then in the color of the most recent card. When
        a new card is tapped the square updates to the new color.
        """
        if not self._nfc_ready:
            raise RuntimeError("NFC not initialised")

        if animate:
            if self._last_card_color is None:
                self.pixels_center_square((4, 4, 4))    # never-tapped: faint white
            else:
                rgb = self._FAINT_CARD_RGB.get(self._last_card_color, (4, 4, 4))
                self.pixels_center_square(rgb)

        start = time.ticks_ms()
        while True:
            now = time.ticks_ms()

            if timeout_ms is not None and \
                    time.ticks_diff(now, start) > timeout_ms:
                return None

            if self._detect_tag(timeout=200):
                try:
                    page = self._read_page(5)
                    raw_color = page[1]
                    color  = _raw_to_app_color(raw_color)
                    serial = (page[2] << 8) | page[3]
                    self._last_card_color = color
                    if animate:
                        rgb = self._FAINT_CARD_RGB.get(color, (1, 1, 1))
                        self.pixels_center_square(rgb)
                    return color, serial
                except RuntimeError:
                    pass

            time.sleep_ms(100)

    def read_card_named(self, timeout_ms=None, animate=True):
        r = self.read_card(timeout_ms, animate)
        if r is None: return None
        color, serial = r
        return color, CARD_COLOR_NAMES.get(color, '?'), serial

    # ── lazy accessors for optional drivers ─────────────
    @property
    def accel(self):
        if not hasattr(self, '_accel'):
            from lis2dw12 import LIS2DW12
            self._accel = LIS2DW12(self.i2c, addr=ACCEL_ADDR)
            self._accel.init()
        return self._accel

    @property
    def light(self):
        if not hasattr(self, '_light'):
            from opt3002 import OPT3002
            self._light = OPT3002(self.i2c, addr=LIGHT_ADDR)
            self._light.init()
        return self._light

    @property
    def battery(self):
        if not hasattr(self, '_batt'):
            from max17048 import MAX17048
            self._batt = MAX17048(self.i2c, addr=BATT_ADDR)
        return self._batt


# Quick demo if run directly
if __name__ == '__main__':
    w = Wand()
    print("Tap a LEGO Connection Card...")
    while True:
        card = w.read_card_named()
        if card is None: continue
        color, name, serial = card
        print("→ {}  (color {}, serial {:04d})".format(name, color, serial))
        w.beep(1200, 80)
        time.sleep(1)