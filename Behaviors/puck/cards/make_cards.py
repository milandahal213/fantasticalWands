"""
make_cards.py — generate printable behavior cards (behavior_cards.pdf).

Pulls each behavior's NAME + REQUIRED straight from the puck code (so they stay
in sync) and lays them out as cut-out cards, 6 per US-Letter page.

    python cards/make_cards.py        # writes cards/behavior_cards.pdf
"""
import os
import sys

from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

# import the real registry (behaviors/ has no hardware deps beyond util)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from behaviors import BEHAVIORS  # noqa: E402

KIND_LABEL = {
    "single_motor": "Single Motor",
    "double_motor": "Double Motor",
    "color_sensor": "Color Sensor",
    "controller": "Controller",
}
KIND_DOT = {
    "single_motor": HexColor("#f57d20"),
    "double_motor": HexColor("#2a7d8c"),
    "color_sensor": HexColor("#c0392b"),
    "controller": HexColor("#1e4f82"),
}

# The deck: which cards to print (in order) + their accent color and blurb.
# Each key must be a behavior in behaviors/__init__.py (NAME + REQUIRED are
# pulled from the code). Edit this dict to change which cards get printed.
CARDS = {
    "tank_drive":      ("#1e4f82", "Left stick drives the left wheel, right stick the right. "
                                   "Push both to go straight, opposite to spin on the spot."),
    "arcade_drive":    ("#1e4f82", "Right stick is the gas, left stick steers. "
                                   "Easy one-hand driving."),
    "precision_turn":  ("#163a61", "Flick the right stick left or right to spin exactly in place. "
                                   "It beeps when the turn is finished."),
    "color_gearbox":   ("#2a7d8c", "Show it a color to pick a gear — green = fast, "
                                   "yellow = half, red = reverse — then drive as normal."),
    "motor_knob":      ("#f57d20", "Turn the single motor by hand and the drive motor copies "
                                   "it, moving to the same position. Let go and it holds."),
    "position_control":           ("#8e44ad", "Put wheels on a Double Motor. The Double Motor is "
                                   "preprogramed to dance. Watch and enjoy!"),
}

PAGE_W, PAGE_H = letter
MARGIN = 36
GUTTER = 18
COLS, ROWS = 2, 3
CARD_W = (PAGE_W - 2 * MARGIN - (COLS - 1) * GUTTER) / COLS
CARD_H = (PAGE_H - 2 * MARGIN - (ROWS - 1) * GUTTER) / ROWS
PAD = 14
BAND_MIN = 42


def light(hex_color, keep):
    """Blend toward white; keep=0 -> white, keep=1 -> full color."""
    c = HexColor(hex_color)
    r = c.red * 255 * keep + 255 * (1 - keep)
    g = c.green * 255 * keep + 255 * (1 - keep)
    b = c.blue * 255 * keep + 255 * (1 - keep)
    return HexColor("#%02x%02x%02x" % (int(r), int(g), int(b)))


def wrap(text, font, size, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_title(text, max_w, max_size=17, min_size=11):
    """Largest size (<= max_size) that fits in <= 2 lines."""
    for size in range(max_size, min_size - 1, -1):
        lines = wrap(text, "Helvetica-Bold", size, max_w)
        if len(lines) <= 2:
            return size, lines
    return min_size, wrap(text, "Helvetica-Bold", min_size, max_w)


def draw_card(c, x, y, key, mod):
    accent = CARDS[key][0]
    desc = CARDS[key][1]
    name = mod.NAME
    required = mod.REQUIRED
    inner_w = CARD_W - 2 * PAD

    # card background + border
    c.setFillColor(light(accent, 0.06))
    c.setStrokeColor(HexColor("#c9c2b6"))
    c.setLineWidth(1)
    c.roundRect(x, y, CARD_W, CARD_H, 10, stroke=1, fill=1)

    # header band (height grows for 2-line titles)
    size, lines = fit_title(name, inner_w)
    band_h = BAND_MIN + (16 if len(lines) > 1 else 0)
    c.setFillColor(HexColor(accent))
    c.roundRect(x, y + CARD_H - band_h, CARD_W, band_h, 10, stroke=0, fill=1)
    c.setFillColor(HexColor(accent))
    c.rect(x, y + CARD_H - band_h, CARD_W, band_h - 10, stroke=0, fill=1)  # square off bottom
    c.setFillColor(white)
    ty = y + CARD_H - (band_h / 2) + (size * (len(lines)) / 2) - size + 3
    for i, ln in enumerate(lines):
        c.setFont("Helvetica-Bold", size)
        c.drawCentredString(x + CARD_W / 2, ty - i * (size + 2), ln)

    cy = y + CARD_H - band_h - 16

    # config key (mono)
    c.setFont("Courier", 8.5)
    c.setFillColor(HexColor("#6b5d4e"))
    c.drawString(x + PAD, cy, 'BEHAVIOR = "%s"' % key)
    cy -= 16

    # device pills
    px, py = x + PAD, cy
    for kind in required:
        label = KIND_LABEL.get(kind, kind)
        w = stringWidth(label, "Helvetica", 8) + 22
        if px + w > x + CARD_W - PAD:
            px = x + PAD
            py -= 20
        c.setFillColor(light(accent, 0.16))
        c.setStrokeColor(light(accent, 0.5))
        c.roundRect(px, py - 12, w, 16, 8, stroke=1, fill=1)
        c.setFillColor(KIND_DOT.get(kind, HexColor("#888888")))
        c.circle(px + 9, py - 4, 3.2, stroke=0, fill=1)
        c.setFillColor(HexColor("#3a2f22"))
        c.setFont("Helvetica", 8)
        c.drawString(px + 15, py - 6.5, label)
        px += w + 6
    cy = py - 26

    # description
    c.setFillColor(HexColor("#1a1008"))
    for ln in wrap(desc, "Helvetica", 9.5, inner_w):
        c.setFont("Helvetica", 9.5)
        c.drawString(x + PAD, cy, ln)
        cy -= 13

    # footer
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(HexColor("#9a8f7d"))
    n = len(required)
    c.drawString(x + PAD, y + 10, "puck behavior · needs %d device%s" % (n, "" if n == 1 else "s"))


def main():
    out = os.path.join(HERE, "behavior_cards.pdf")
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle("Puck Behavior Cards")

    per_page = COLS * ROWS
    keys = [k for k in CARDS if k in BEHAVIORS]   # the deck, in CARDS order
    missing = [k for k in CARDS if k not in BEHAVIORS]
    if missing:
        print("warning: skipping cards with no matching behavior:", missing)
    for i, key in enumerate(keys):
        slot = i % per_page
        if i and slot == 0:
            c.showPage()
        col = slot % COLS
        row = slot // COLS
        x = MARGIN + col * (CARD_W + GUTTER)
        y = PAGE_H - MARGIN - (row + 1) * CARD_H - row * GUTTER
        draw_card(c, x, y, key, BEHAVIORS[key])
    c.showPage()
    c.save()
    print("wrote", out, "(%d cards)" % len(keys))


if __name__ == "__main__":
    main()
