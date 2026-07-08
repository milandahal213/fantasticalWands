"""
matrix.py — 5x5 NeoPixel status display for the box.

The grid is 25 WS2812 pixels, row-major:
    row 0 = pixels  0.. 4   (top)
    ...
    row 4 = pixels 20..24   (bottom)

Layout used here:
    Bottom row (20..24)  = battery gauge: 1 bar per 20%, colored by level.
    Rows 0..3 (0..19)    = "comm" area: scan / found / connect-progress / running.

Exposes the same methods as the puck's status.Status (breathe_step, flash,
set_progress, running, blink, low_battery, error) so main.py stays almost
identical — plus set_battery(soc) to paint the bottom row.

Physical orientation varies by wiring: if the battery gauge ends up at the top,
flip BATTERY_PIXELS / COMM_PIXELS below.
"""

import time
import machine
import neopixel

_MAX_VAL = 50     # brightest any channel gets (0-255)
_FLOOR_F = 0.30   # breathe dims to this fraction of peak
_STEP = 0.06

GRID = 5
N = GRID * GRID                          # 25 pixels
# Set True if the grid is wired zig-zag (alternate rows reversed). Default
# row-major (pixel = row*5 + col), matching the project's wand grid.
SERPENTINE = False


def xy(row, col):
    """(row, col) -> pixel index. row 0 = top, row 4 = bottom."""
    if SERPENTINE and (row % 2 == 1):
        col = GRID - 1 - col
    return row * GRID + col


BATTERY_PIXELS = tuple(xy(GRID - 1, c) for c in range(GRID))          # bottom row
PROGRESS_PIXELS = tuple(xy(0, c) for c in range(GRID))                # top row
COMM_PIXELS = tuple(xy(r, c) for r in range(GRID - 1) for c in range(GRID))  # rows 0..3


def _battery_color(soc):
    if soc >= 80:
        return (0, 255, 0)
    if soc >= 40:
        return (255, 255, 0)
    if soc >= 20:
        return (255, 120, 0)
    return (255, 0, 0)


class Matrix:
    def __init__(self, pin, base_rgb):
        self.np = neopixel.NeoPixel(machine.Pin(pin), N)
        self.locked = 0
        self._f = _FLOOR_F
        self._dir = 1
        self._batt = [(0, 0, 0)] * len(BATTERY_PIXELS)   # cached bottom row
        self.set_base(base_rgb)

    # ── config ──
    def set_base(self, rgb):
        self.base = self._cap(rgb)

    def set_progress(self, locked):
        self.locked = locked if locked < len(PROGRESS_PIXELS) else len(PROGRESS_PIXELS)
        self._render()

    def set_battery(self, soc):
        """Paint the bottom row: one lit bar per 20%, colored by level."""
        col = self._cap(_battery_color(soc))
        lit = int(soc / 20.0 + 0.5)
        if lit < 0:
            lit = 0
        elif lit > len(BATTERY_PIXELS):
            lit = len(BATTERY_PIXELS)
        self._batt = [col if i < lit else (0, 0, 0) for i in range(len(BATTERY_PIXELS))]
        self._render()

    # ── animations (comm area) ──
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
        for i in COMM_PIXELS:
            self.np[i] = (_MAX_VAL, _MAX_VAL, _MAX_VAL)
        self.np.write()
        time.sleep_ms(60)
        self._render()

    def running(self):
        self.locked = len(PROGRESS_PIXELS)
        for i in COMM_PIXELS:
            self.np[i] = self.base
        self._paint_battery()
        self.np.write()

    def blink(self, rgb, times=3, on_ms=220, off_ms=160):
        """Blink the whole grid a color (capped), then restore."""
        c = self._cap(rgb)
        for _ in range(times):
            for i in range(N):
                self.np[i] = c
            self.np.write()
            time.sleep_ms(on_ms)
            for i in range(N):
                self.np[i] = (0, 0, 0)
            self.np.write()
            time.sleep_ms(off_ms)
        self._render()

    def low_battery(self, times=2):
        self.blink((255, 0, 0), times=times, on_ms=150, off_ms=150)

    def clear(self):
        for i in range(N):
            self.np[i] = (0, 0, 0)
        self.np.write()

    def error(self):
        while True:
            for i in range(N):
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

    def _paint_battery(self):
        for j, pix in enumerate(BATTERY_PIXELS):
            self.np[pix] = self._batt[j]

    def _render(self):
        breathe = self._scale(self.base, self._f)
        for pos, pix in enumerate(COMM_PIXELS):
            if pix in PROGRESS_PIXELS and PROGRESS_PIXELS.index(pix) < self.locked:
                self.np[pix] = self.base
            else:
                self.np[pix] = breathe
        self._paint_battery()
        self.np.write()
