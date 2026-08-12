"""
broadcast_main.py - default behavior. Read a local input and BROADCAST it to
LEGO motors (connectionless - no GATT, drives any listening motor).

Pins:
  GP0/1   NFC reader (WS1850S)  - tap a card to pick which motor(s) to drive
  GP4/5   I2C bus               - OLED and/or an I2C sensor (see sensors.py)
  GP26/27 analog (ADC0/ADC1)    - two pots / voltage dividers = left / right
  GP28    NeoPixel              - shows the tapped card's color

Control input priority (per loop):
  - a recognized I2C sensor present (either bus) -> it drives; ANALOG IGNORED
  - else -> analog GP26/27 (deflection from a startup baseline) drives L/R
  - OLED (if present) just shows the values

Broadcast target = the card you tap on the NFC reader (color+serial+UID->hash).
Tap again anytime to switch groups. Until a card is tapped, a default is used.
"""

from machine import Pin, SoftI2C, ADC
import neopixel
import time

from lego_broadcast import Broadcaster
from ws1850s import WS1850S
import nfc_serial
import font5x7
import sensors

# ---- config -------------------------------------------------------------
DEFAULT_COLOR = 0x02       # used until a card is tapped
DEFAULT_SERIAL = 1126

NFC_SDA, NFC_SCL = 0, 1    # GP0/GP1
BUS_SDA, BUS_SCL = 4, 5    # GP4/GP5 (OLED or I2C sensor)
I2C_FREQ = 100_000

OLED_ADDRS = (0x3C, 0x3D)
OLED_W, OLED_H = 64, 64
OLED_Y_OFFSET = 16         # this panel shows only the bottom ~48 rows
LINE_PITCH = 8

# Recognized I2C input sensors are defined in sensors.py (lookup table +
# whoami verification). When one is present it drives and the analog pins are
# ignored; it may be on EITHER bus (GP4/5 or the NFC bus GP0/1).

ADC_LEFT_PIN = 26          # GP26 (ADC0) -> LEFT motor speed
ADC_RIGHT_PIN = 27         # GP27 (ADC1) -> RIGHT motor speed
ANALOG_SPAN = 16000        # ADC counts of change from the startup baseline that
                           # = full speed. Tune from the "raw n/n" the OLED/REPL
                           # prints: set it near your LDR's dark<->bright swing.
ANALOG_SAMPLES = 16        # average N reads/loop (RP2040 ADC + high-Z LDR is noisy)
ANALOG_DEADZONE = 4000     # ignore drift within this many counts of baseline
                           # (kills resting jitter; raise if it still twitches)
BROADCAST_MS = 40          # ~25 Hz
# NFC polling is adaptive: an EMPTY reader is cheap to poll (a WUPA that finds
# nothing returns almost instantly), so we poll it fast to catch a new tap right
# away. A card sitting ON the reader costs a full slow transaction (anticoll +
# select + 16-byte read) - re-reading that every loop stalls the control loop and
# makes the analog feel laggy, so once a card is present we poll it rarely.
NFC_POLL_EMPTY_MS = 60     # reader empty -> poll fast (catch a tap immediately)
NFC_POLL_HELD_MS = 300     # card present -> poll rarely (keep the loop snappy)

# Motors are mounted mirror-image, so a forward command must be negated to
# drive properly. Both by default; flip one to False if the robot spins instead
# of going straight, or if a side runs the wrong way.
INVERT_LEFT = False
INVERT_RIGHT = True

NEO_PIN = 28               # WS2812 NeoPixel: shows the tapped card's color
NEO_COUNT = 1
NEO_BRIGHTNESS = 0.4       # scale so full white isn't blinding / power-hungry

# LEGO firmware color code -> RGB (from legoeducation color_map hex values).
_COLOR_RGB = {
    0: (0, 0, 0), 1: (228, 89, 158), 2: (75, 47, 145), 3: (0, 108, 184),
    4: (120, 191, 234), 5: (0, 180, 160), 6: (97, 168, 54), 7: (255, 212, 0),
    8: (245, 125, 32), 9: (222, 26, 33), 10: (255, 255, 255),
}
REDETECT_MS = 800          # re-scan GP4/5 and re-check NFC this often

# ---- setup --------------------------------------------------------------
# A SHORT SoftI2C timeout matters here: with NOTHING plugged into GP4/5 the bus
# floats, and the default 50ms clock-stretch timeout then stalls every scan()
# for ages (this is why the loop crawled in analog-only mode but felt snappy
# with a Qwiic joystick/OLED plugged in - those boards pull the bus up). We also
# enable the RP2040's internal pull-ups below so a bare bus doesn't float at all.
I2C_TIMEOUT_US = 2000
nfc_i2c = SoftI2C(scl=Pin(NFC_SCL), sda=Pin(NFC_SDA), freq=I2C_FREQ, timeout=I2C_TIMEOUT_US)
reader = WS1850S(nfc_i2c)
bus = SoftI2C(scl=Pin(BUS_SCL), sda=Pin(BUS_SDA), freq=I2C_FREQ, timeout=I2C_TIMEOUT_US)

# Turn on internal pull-ups for both buses so an unpopulated bus reads cleanly
# (returns "no devices" fast) instead of floating and hanging on the timeout.
# The pins keep the open-drain mode SoftI2C set; this only adds the pull resistor.
for _p in (NFC_SDA, NFC_SCL, BUS_SDA, BUS_SCL):
    Pin(_p, Pin.OPEN_DRAIN, Pin.PULL_UP, value=1)   # value=1 = line released (high-Z)
adc_left = ADC(Pin(ADC_LEFT_PIN))
adc_right = ADC(Pin(ADC_RIGHT_PIN))
np = neopixel.NeoPixel(Pin(NEO_PIN), NEO_COUNT)


def set_pixel(color_code):
    """Light the NeoPixel with a LEGO firmware color code."""
    r, g, b = _COLOR_RGB.get(color_code, (30, 30, 30))
    rgb = (int(r * NEO_BRIGHTNESS), int(g * NEO_BRIGHTNESS), int(b * NEO_BRIGHTNESS))
    for i in range(NEO_COUNT):
        np[i] = rgb
    np.write()


def _clip(v):
    v = int(v)
    return -100 if v < -100 else 100 if v > 100 else v


def _read_avg(adc):
    """Averaged ADC read (the raw value is noisy with a high-impedance LDR)."""
    s = 0
    for _ in range(ANALOG_SAMPLES):
        s += adc.read_u16()
    return s // ANALOG_SAMPLES


def _analog_speed(raw, base):
    """Deflection from baseline -> speed. Readings within +/-ANALOG_DEADZONE of
    the baseline read as 0; past that the speed ramps up *from zero* at the
    deadzone edge (we subtract the deadzone before scaling) so there's no sudden
    jump to a big value the moment you leave the deadzone."""
    d = raw - base
    if d > ANALOG_DEADZONE:
        d -= ANALOG_DEADZONE
    elif d < -ANALOG_DEADZONE:
        d += ANALOG_DEADZONE
    else:
        return 0
    return _clip(d * 100 // ANALOG_SPAN)


def _baseline(adc, n=16):
    """Average a few reads to capture the resting value as the zero point."""
    s = 0
    for _ in range(n):
        s += adc.read_u16()
        time.sleep_ms(2)
    return s // n


def make_oled(addrs):
    from ssd1306 import SSD1306_I2C
    for a in OLED_ADDRS:
        if a in addrs:
            try:
                return SSD1306_I2C(OLED_W, OLED_H, bus, addr=a)
            except Exception:
                pass
    return None


def show(oled, *lines):
    print("[status]", " | ".join(str(t) for t in lines if t != ""))
    if oled is None:
        return
    oled.fill(0)
    for row, text in enumerate(lines[:6]):
        font5x7.text(oled, str(text)[:10], 0, OLED_Y_OFFSET + row * LINE_PITCH)
    oled.show()


def main():
    bc = Broadcaster(DEFAULT_COLOR, DEFAULT_SERIAL)
    have_card = False
    addrs = []
    oled = None
    sensor = None          # (bus, addr, descriptor) of the active input sensor
    sensor_base = None     # captured resting reading for needs_baseline sensors
    last_detect = 0
    last_nfc = 0           # NFC is polled on its own adaptive cadence
    card_present = False   # was a card on the reader at the last NFC poll?
    last_scan = None       # print I2C scan only when it changes

    # Capture the resting analog values at startup as the zero baseline.
    base_left = _baseline(adc_left)
    base_right = _baseline(adc_right)
    print("Analog baseline: L=%d R=%d" % (base_left, base_right))

    set_pixel(0)   # start dark until a card is tapped
    show(None, "Broadcast", "tap a card")
    print("Broadcasting. Tap a card to pick the motor group. Ctrl-C to stop.")

    try:
        while True:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_detect) > REDETECT_MS:
                last_detect = now
                sa = sensors.scan_addrs(bus)
                sb = sensors.scan_addrs(nfc_i2c)
                if (sa, sb) != last_scan:            # print scan when it changes
                    print("I2C  GP4/5:", [hex(a) for a in sa],
                          " GP0/1:", [hex(a) for a in sb])
                    last_scan = (sa, sb)
                addrs = sa
                if oled is None:
                    oled = make_oled(addrs)          # hot-plug OLED
                # find a recognized input sensor on either bus (sensors.py).
                # Reuse the scans we just did (sa/sb) - don't re-scan the buses.
                found = None
                for b, ba in ((bus, sa), (nfc_i2c, sb)):
                    hits = sensors.identify(b, ba)
                    if hits:
                        found = (b, hits[0][0], hits[0][1])
                        break
                if found is None:
                    sensor = None
                    sensor_base = None
                elif sensor is None or found[1] != sensor[1]:
                    sensor = found                   # new sensor -> (re)capture baseline
                    sensor_base = (sensors.baseline(*sensor)
                                   if sensor[2].get("needs_baseline") else None)

            # Poll the NFC reader on its OWN adaptive cadence (not gated behind
            # the 800ms I2C rescan): fast while the reader is empty so a tap is
            # caught right away, slow while a card is held so the slow read
            # doesn't stall the analog control loop.
            poll_ms = NFC_POLL_HELD_MS if card_present else NFC_POLL_EMPTY_MS
            if time.ticks_diff(now, last_nfc) > poll_ms:
                last_nfc = now
                card = nfc_serial.read_card_full_now(reader)   # (uid, serial, color)
                card_present = card is not None
                if card:
                    bc.set_card(card[0], card[1], card[2])     # uid -> beacon hash
                    set_pixel(card[2])                         # NeoPixel = card color
                    have_card = True

            if sensor is not None:                   # I2C sensor drives; analog ignored
                b, addr, desc = sensor
                left, right = desc["drive"](desc["read"](b, addr), sensor_base)
                lines = [desc["short"], "L %d" % left, "R %d" % right]
            else:
                rl = _read_avg(adc_left)             # GP26/ADC0 -> left wheel
                rr = _read_avg(adc_right)            # GP27/ADC1 -> right wheel
                left = _analog_speed(rl, base_left)
                right = _analog_speed(rr, base_right)
                lines = ["Analog", "L %d R %d" % (left, right),
                         "raw %d/%d" % (rl, rr)]

            l_out = -left if INVERT_LEFT else left     # mirror-mounted motors
            r_out = -right if INVERT_RIGHT else right
            bc.emit(l_out, r_out)
            tag = ("#%d" % bc.serial) if have_card else "#%d?" % bc.serial
            show(oled, *(lines + ["", "card " + tag]))
            time.sleep_ms(BROADCAST_MS)
    except KeyboardInterrupt:
        bc.stop()
        show(oled, "Stopped")
        print("Stopped broadcasting.")


if __name__ == "__main__":
    main()
