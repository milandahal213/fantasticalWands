# wand_ui.py — LED display rules for the 5x5 NeoPixel grid.
#
# Layout:
#   Row 0  (pixels  0..4):
#       pixel 0      = pairing card color (bound card indicator)
#       pixels 1..4  = device status (up to 4 devices)
#
#   Rows 1..4 (pixels 5..24): one row per rule (max 4 rules)
#       pixel 0 of row = trigger type color
#       pixels 1..4    = action colors (up to 4 actions per rule)
#
# Trigger colors:
#   Wand events (button, shake)  = YELLOW
#   Controller events            = DARK DEEP RED
#   Color sensor events          = PINK
#
# Action colors:
#   Single motor actions         = LIGHT GREEN
#   Double motor actions         = DARK GREEN
#   Empty slot                   = OFF

import time
import machine

MAX_DEVICES = 4   # pixels 1..4 on row 0
MAX_RULES   = 4   # one row per rule (rows 1..4)
MAX_BODY    = 4   # actions per rule (pixels 1..4 per row)

VIBRATION_PIN = 21

# Row 0 pixel indices
CARD_PIXEL   = 0           # pixel 0 = bound card color
DEVICE_PIXELS = (1, 2, 3, 4)  # pixels 1-4 = device status

# Rule rows: starting pixel index of each rule row
RULE_ROW_START = (5, 10, 15, 20)   # rows 1..4

# Pixels used for spinner (row 1 = first rule row when no rules yet)
# Walk perimeter of rows 1..3 clockwise
SPINNER_PATH = (5, 6, 7, 8, 9, 14, 19, 18, 17, 16, 15, 10)
ANIM_PIXELS  = tuple(range(5, 25))   # rows 1..4 (20 pixels)


# ── Fixed colors ──────────────────────────────────────────────────────

COLOR_SPINNER        = (10, 10, 10)   # white spinner head
COLOR_SPINNER_TRAIL  = ( 3,  3,  3)   # faint white trail
COLOR_SPINNER_BG     = ( 1,  1,  1)   # barely-on background
COLOR_DEVICE_SOLID   = ( 5,  8,  2)   # connected device
COLOR_DEVICE_BLINK   = ( 5,  8,  2)   # finding (toggled on/off)
COLOR_FLASH          = (10, 10, 10)   # white flash

# Trigger pixel colors (first pixel of each rule row)
COLOR_TRIGGER_WAND        = (10, 10,  0)  # yellow  — button / shake
COLOR_TRIGGER_CONTROLLER  = ( 8,  0,  2)  # dark deep red — joystick
COLOR_TRIGGER_COLOR       = (10,  3,  6)  # pink    — color sensor

# Action pixel colors (pixels 1..4 of each rule row)
COLOR_ACTION_SINGLE_MOTOR = ( 3, 10,  3)  # light green
COLOR_ACTION_DOUBLE_MOTOR = ( 0,  6,  0)  # dark green
COLOR_ACTION_OFF          = ( 0,  0,  0)  # empty slot

# Pairing card palette for pixel 0 (final PWM values, peak channel 10)
CARD_COLORS = {
    1: (10,  2,  6),   # MAGENTA
    2: ( 3,  0, 10),   # PURPLE
    3: ( 0,  1, 10),   # BLUE
    4: ( 0,  5, 10),   # AZURE
    5: ( 0, 10,  5),   # TURQUOISE
    6: ( 0, 10,  0),   # GREEN
    7: (10, 10,  0),   # YELLOW
    8: (10,  5,  0),   # ORANGE
    9: (10,  0,  0),   # RED
    10:(10, 10, 10),   # WHITE
}

# Maps event op → trigger color
_TRIGGER_COLOR_MAP = {
    'check_button':     COLOR_TRIGGER_WAND,
    'check_shake':      COLOR_TRIGGER_WAND,
    'check_controller': COLOR_TRIGGER_CONTROLLER,
    'check_color':      COLOR_TRIGGER_COLOR,
}

# Maps action op → action color
_ACTION_COLOR_MAP = {
    'run_single':   COLOR_ACTION_SINGLE_MOTOR,
    'stop_single':  COLOR_ACTION_SINGLE_MOTOR,
    'single_angle': COLOR_ACTION_SINGLE_MOTOR,
    'keep_moving':  COLOR_ACTION_DOUBLE_MOTOR,
    'stop_double':  COLOR_ACTION_DOUBLE_MOTOR,
    'turn':         COLOR_ACTION_DOUBLE_MOTOR,
    'move':         COLOR_ACTION_DOUBLE_MOTOR,
}


def _trigger_color(opcode):
    return _TRIGGER_COLOR_MAP.get(opcode.get('op'), COLOR_TRIGGER_WAND)


def _action_color(opcode):
    return _ACTION_COLOR_MAP.get(opcode.get('op'), COLOR_ACTION_OFF)


class WandUI:
    """Owner of the 5x5 NeoPixel grid."""

    BLINK_PERIOD_MS = 400
    SPINNER_STEP_MS = 80

    def __init__(self, wand, card_color=None):
        self.wand = wand
        self.np   = wand.np
        self.card_color  = card_color
        self.connected   = [False] * MAX_DEVICES
        self.finding     = [False] * MAX_DEVICES
        self._spinner_phase = 0

        try:
            self._vibe = machine.Pin(VIBRATION_PIN, machine.Pin.OUT)
            self._vibe.value(0)
        except Exception as e:
            print("vibe init failed:", e)
            self._vibe = None

    # ── card color ──────────────────────────────────────────────────
    def set_card_color(self, color_id):
        self.card_color = color_id
        self._render_card_pixel()
        self._push()

    def _card_rgb(self):
        if self.card_color is None:
            return (0, 0, 0)
        return CARD_COLORS.get(self.card_color, (0, 0, 0))

    def _render_card_pixel(self):
        """Paint pixel 0 with the bound card color."""
        self.np[CARD_PIXEL] = self._card_rgb()

    # ── vibration ───────────────────────────────────────────────────
    def vibrate(self, duration_ms=50):
        if self._vibe is None: return
        self._vibe.value(1)
        time.sleep_ms(duration_ms)
        self._vibe.value(0)

    def vibrate_pattern(self, pattern):
        if self._vibe is None: return
        for on_ms, off_ms in pattern:
            self._vibe.value(1); time.sleep_ms(on_ms)
            self._vibe.value(0); time.sleep_ms(off_ms)

    # ── low-level helpers ───────────────────────────────────────────
    def _push(self):
        self.np.write()

    def clear_all(self):
        for i in range(25): self.np[i] = (0, 0, 0)
        self._push()

    def _clear_rules_area(self):
        """Clear all rule rows (pixels 5..24)."""
        for i in ANIM_PIXELS: self.np[i] = (0, 0, 0)

    # ── top row: card pixel + device status ────────────────────────
    def device_count(self):
        return sum(1 for c in self.connected if c)

    def _next_free_slot(self):
        for i in range(MAX_DEVICES):
            if not self.connected[i] and not self.finding[i]:
                return i
        return None

    def mark_finding(self):
        i = self._next_free_slot()
        if i is None: return None
        self.finding[i] = True
        return i

    def mark_connected(self, slot_index):
        if slot_index is None: return
        if 0 <= slot_index < MAX_DEVICES:
            self.finding[slot_index]   = False
            self.connected[slot_index] = True

    def mark_failed(self, slot_index):
        if slot_index is None: return
        if 0 <= slot_index < MAX_DEVICES:
            self.finding[slot_index] = False

    def render_top_row(self):
        """Repaint row 0: pixel 0 = card color, pixels 1-4 = device status."""
        # Pixel 0: pairing card color
        self._render_card_pixel()

        # Pixels 1-4: device status
        blink_on = (time.ticks_ms() // (self.BLINK_PERIOD_MS // 2)) & 1
        for i, pix in enumerate(DEVICE_PIXELS):
            if self.connected[i]:
                self.np[pix] = COLOR_DEVICE_SOLID
            elif self.finding[i] and blink_on:
                self.np[pix] = COLOR_DEVICE_BLINK
            else:
                self.np[pix] = (0, 0, 0)

    def clear_animation(self):
        """Clear rule rows, redraw top row."""
        self._clear_rules_area()
        self.render_top_row()
        self._push()

    # ── animations ─────────────────────────────────────────────────
    def card_tap_intro(self, ms=300):
        """Brief tint of rule rows in bound card color."""
        rgb = self._card_rgb()
        for i in ANIM_PIXELS: self.np[i] = rgb
        self._push()
        time.sleep_ms(ms)
        self._clear_rules_area()
        self.render_top_row()
        self._push()

    def tick_spinner(self):
        """One frame of the scanning spinner."""
        for i in ANIM_PIXELS: self.np[i] = COLOR_SPINNER_BG
        n    = len(SPINNER_PATH)
        head = SPINNER_PATH[self._spinner_phase % n]
        tail = SPINNER_PATH[(self._spinner_phase - 1) % n]
        self.np[tail] = COLOR_SPINNER_TRAIL
        self.np[head] = COLOR_SPINNER
        self.render_top_row()
        self._push()
        self._spinner_phase += 1

    def flash_anim(self, flashes=2, on_ms=80, off_ms=80):
        """Quick white flash in rule rows."""
        for _ in range(flashes):
            for i in ANIM_PIXELS: self.np[i] = COLOR_FLASH
            self.render_top_row(); self._push()
            time.sleep_ms(on_ms)
            self._clear_rules_area()
            self.render_top_row(); self._push()
            time.sleep_ms(off_ms)

    def flash_block_ack(self, rgb, on_ms=120, off_ms=60):
        """Double-flash rule rows in rgb. Used on card-tap confirmation."""
        for _ in range(2):
            for i in ANIM_PIXELS: self.np[i] = rgb
            self.render_top_row(); self._push()
            time.sleep_ms(on_ms)
            self._clear_rules_area()
            self.render_top_row(); self._push()
            time.sleep_ms(off_ms)

    def tick_idle(self):
        """One frame of the 'ready to pair' indicator.
        Slowly breathes the center pixel (12) white. Call in the main
        loop when no card is connected and no card is being scanned."""
        # 3-second triangle wave: brightness 0→5→0
        t = time.ticks_ms() % 3000
        level = t if t < 1500 else 3000 - t   # 0..1500..0
        bright = level * 5 // 1500             # 0..5
        self.np[12] = (bright, bright, bright)
        self.np.write()

    def wipe_anim(self, rgb=(10, 0, 0), step_ms=40):
        """Sweep rgb across rule rows left-to-right, then clear. Used for ERASE."""
        for i in ANIM_PIXELS:
            self.np[i] = rgb
            self.render_top_row(); self._push()
            time.sleep_ms(step_ms)
        time.sleep_ms(150)
        self._clear_rules_area()
        self.render_top_row(); self._push()

    def show_battery(self, soc, hold_ms=3000):
        """Show battery level across all 25 pixels, hold for hold_ms, then restore.
        
        soc: state of charge 0.0–100.0
        Color: green (>=60%), yellow (>=30%), red (<30%)
        LEDs lit: proportional (25 = full, 0 = empty, always at least 1 if >0%)
        """
        if soc >= 60:
            color = ( 0, 10,  0)  # green
        elif soc >= 30:
            color = (10, 10,  0)  # yellow
        else:
            color = (10,  0,  0)  # red

        lit = max(1, int(soc / 100.0 * 25)) if soc > 0 else 0

        for i in range(25):
            self.np[i] = color if i < lit else (0, 0, 0)
        self._push()
        time.sleep_ms(hold_ms)

        # Restore top row (caller restores rule rows via paint_deck)
        self.render_top_row()
        self._push()

    # ── programming display ─────────────────────────────────────────
    def _paint_rule_row(self, row_idx, rule, dim=False):
        """Paint one rule into its row.
        row_idx: 0..3 (maps to rows 1..4, starting pixels 5/10/15/20)
        rule: {'event': opcode, 'body': [opcodes]}
        dim: if True, render at 1/4 brightness (for non-firing rules during run)
        """
        
        start = RULE_ROW_START[row_idx]

        # Pixel 0 of row = trigger color
        trig = _trigger_color(rule['event'])
        if dim:
            trig = (trig[0] // 4, trig[1] // 4, trig[2] // 4)
        self.np[start] = trig

        # Pixels 1..4 = action colors
        for j in range(MAX_BODY):
            pix = start + 1 + j
            if j < len(rule['body']):
                act = _action_color(rule['body'][j])
                if dim:
                    act = (act[0] // 4, act[1] // 4, act[2] // 4)
            else:
                act = COLOR_ACTION_OFF
            self.np[pix] = act

    def paint_deck(self, program):
        """Paint rows 1..4 to show all rules. Empty rows are off."""
        self._clear_rules_area()
        for i, rule in enumerate(program):
            if i >= MAX_RULES: break
            self._paint_rule_row(i, rule)
        self.render_top_row()
        self._push()

    def paint_running(self, program, firing_rule_idx):
        """Paint rules during execution. Firing rule full brightness, others dim."""
        self._clear_rules_area()
        for i, rule in enumerate(program):
            if i >= MAX_RULES: break
            self._paint_rule_row(i, rule, dim=(i != firing_rule_idx))
        self.render_top_row()
        self._push()