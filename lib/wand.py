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

    # ── Button / buzzer ─────────────────────────────────
    def button_pressed(self):
        return self.button.value() == 0

    def beep(self, freq=1000, duration_ms=100):
        self._buzz.freq(freq)
        self._buzz.duty(512)
        time.sleep_ms(duration_ms)
        self._buzz.duty(0)

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
    def read_card(self, timeout_ms=None, animate=True):
        """Wait for a LEGO Connection Card. Returns (color, serial) or None on timeout.

        animate=True shows a breathing 'tap card' prompt and flashes the
        card color on success.
        """
        if not self._nfc_ready:
            raise RuntimeError("NFC not initialised")
        start = time.ticks_ms()
        while True:
            if animate:
                self.pixels_card_prompt()
            if timeout_ms is not None and \
                    time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                if animate: self.pixels_clear()
                return None
            if self._detect_tag():
                try:
                    page = self._read_page(5)
                    color  = page[1]
                    serial = (page[2] << 8) | page[3]
                    if animate:
                        self.pixels_flash_card(color)
                        self.pixels_fill_card(color)
                    return color, serial
                except RuntimeError:
                    pass
            time.sleep_ms(50)

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