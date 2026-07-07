"""
status.py — 3-NeoPixel status display for the puck.

States shown on the strip (base color = the puck's own color):
  breathe_step()      slow breathing — BLE scanning
  flash()             quick white blip — a matching device was found
  set_progress(n)     first n pixels solid (connected), the rest keep breathing
  running()           all pixels solid, bright — required devices connected
  error()             blinking red (fatal), never returns

Designed to be driven by bledevice.discover()'s idle_cb (breathe) and
progress_cb (flash), so it animates even during a blocking scan.
"""

import time
import machine
import neopixel

_MAX_VAL = 50     # brightest any channel ever gets (0-255)
_FLOOR_F = 0.30   # breathe dims to this fraction of peak (never near-off)
_STEP = 0.06      # breathe speed


class Status:
    def __init__(self, pin, count, base_rgb):
        self.np = neopixel.NeoPixel(machine.Pin(pin), count)
        self.n = count
        self.locked = 0          # number of solid ("connected") pixels
        self._f = _FLOOR_F
        self._dir = 1
        self.set_base(base_rgb)

    # ── config ──
    def set_base(self, rgb):
        """Store the color normalized so its brightest channel == _MAX_VAL."""
        self.base = self._cap(rgb)

    def set_progress(self, locked):
        self.locked = locked if locked < self.n else self.n
        self._render()

    # ── animations ──
    def breathe_step(self):
        self._f += self._dir * _STEP
        if self._f >= 1.0:
            self._f = 1.0
            self._dir = -1
        elif self._f <= _FLOOR_F:
            self._f = _FLOOR_F
            self._dir = 1
        self._render()

    def flash(self, *_):
        for i in range(self.n):
            self.np[i] = (_MAX_VAL, _MAX_VAL, _MAX_VAL)
        self.np.write()
        time.sleep_ms(60)
        self._render()

    def running(self):
        self.locked = self.n
        for i in range(self.n):
            self.np[i] = self.base
        self.np.write()

    def clear(self):
        for i in range(self.n):
            self.np[i] = (0, 0, 0)
        self.np.write()

    def error(self):
        while True:
            for i in range(self.n):
                self.np[i] = (_MAX_VAL, 0, 0)
            self.np.write()
            time.sleep_ms(300)
            self.clear()
            time.sleep_ms(300)

    # ── internals ──
    def _cap(self, rgb):
        m = max(rgb) or 1
        f = _MAX_VAL / m
        return (int(rgb[0] * f), int(rgb[1] * f), int(rgb[2] * f))

    def _scale(self, rgb, f):
        return (int(rgb[0] * f), int(rgb[1] * f), int(rgb[2] * f))

    def _render(self):
        breathe = self._scale(self.base, self._f)
        for i in range(self.n):
            self.np[i] = self.base if i < self.locked else breathe
        self.np.write()
