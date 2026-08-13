"""
noWand — desktop app.
Run: python app.py
"""

import io
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

try:
    import cairosvg
    from PIL import Image, ImageTk
    _SVG_SUPPORT = True
except ImportError:
    _SVG_SUPPORT = False

from device_manager import DeviceManager, ScanResult, COLOR_MAP, COLOR_HEX
from lelib import singleMotor, doubleMotor, colorSensor, controller
import behaviors as _behavior_pkg

# ── Theme ─────────────────────────────────────────────────────────────────────
BG          = "#f5f0e8"   # warm tan
BG2         = "#e8e0d0"   # panel background (more contrast)
BG3         = "#d8cfc2"   # input fields, inner elements
FG          = "#1a1008"   # near-black for max readability
FG_DIM      = "#dda76e"   # warm mid-tone (was too light)
ACCENT      = "#1e4f82"   # deeper steel blue (more contrast)
ACCENT_DIM  = "#163a61"
SUCCESS     = "#2e6e42"   # darker green
DANGER      = "#9e2c2c"   # darker red
BORDER      = "#a89880"   # much darker border (was nearly invisible)
SEL_RING    = "#99ea74"

FONT        = "SF Pro Display"
FONT_MONO   = "SF Pro Mono"

RADIUS      = 10          # corner radius used throughout

POLL_MS     = 50

ICON_SIZE      = 100   # px to render each SVG
CARD_ICON_SIZE = 48    # device icon size inside a connected DeviceCard

# Fallback ASCII labels when SVG loading fails (no emoji — crashes Tk on macOS 26)
DEVICE_ICON = {
    'Single Motor': 'M',
    'Double Motor': 'MM',
    'Color Sensor': 'CS',
    'Controller':   'CT',
}

_SVG_FILES = {
    'Single Motor': 'single_motor.svg',
    'Double Motor': 'double_motor.svg',
    'Color Sensor': 'color_sensor.svg',
    'Controller':   'controller.svg',
}

# Populated by load_device_icons(); PhotoImage refs kept to prevent GC.
DEVICE_IMAGES:      dict = {}   # full size (ICON_SIZE px)
DEVICE_IMAGES_SM:   dict = {}   # compact size (scan strip)
DEVICE_IMAGES_CARD: dict = {}   # card size (CARD_ICON_SIZE px)

# Populated by load_emoji_icons(); keyed by color name e.g. 'red', 'magenta'
EMOJI_IMAGES:      dict = {}    # full size
EMOJI_IMAGES_SM:   dict = {}    # compact size (scan strip)
EMOJI_IMAGES_CARD: dict = {}    # card size


def load_device_icons():
    """Render SVG device icons to PhotoImage objects (two sizes)."""
    if not _SVG_SUPPORT:
        print("cairosvg / Pillow not installed — using glyph fallbacks. "
              "Run: pip install cairosvg pillow")
        return
    icon_dir = Path(__file__).parent / "icons"
    for device_type, filename in _SVG_FILES.items():
        svg_path = icon_dir / filename
        if not svg_path.exists():
            continue
        try:
            png = cairosvg.svg2png(url=str(svg_path),
                                   output_width=ICON_SIZE,
                                   output_height=ICON_SIZE)
            full = Image.open(io.BytesIO(png)).convert("RGBA")
            DEVICE_IMAGES[device_type] = ImageTk.PhotoImage(full)

            sm = full.resize((ICON_W_SM - RING_W * 2 - 2,
                               ICON_H_SM - RING_W * 2 - 2),
                              Image.LANCZOS)
            DEVICE_IMAGES_SM[device_type] = ImageTk.PhotoImage(sm)

            card = full.resize((CARD_ICON_SIZE, CARD_ICON_SIZE), Image.LANCZOS)
            DEVICE_IMAGES_CARD[device_type] = ImageTk.PhotoImage(card)
        except Exception as e:
            print(f"Could not load icon {filename}: {e}")


def load_emoji_icons():
    """Render SVG emoji icons (one per card color) to PhotoImage objects."""
    if not _SVG_SUPPORT:
        return
    emoji_dir = Path(__file__).parent / "icons" / "emoji"
    if not emoji_dir.exists():
        return
    for svg_path in emoji_dir.glob("*.svg"):
        color_name = svg_path.stem  # e.g. 'red', 'magenta'
        try:
            png = cairosvg.svg2png(url=str(svg_path),
                                   output_width=ICON_SIZE,
                                   output_height=ICON_SIZE)
            full = Image.open(io.BytesIO(png)).convert("RGBA")
            EMOJI_IMAGES[color_name] = ImageTk.PhotoImage(full)

            sm = full.resize((EMOJI_SM_SZ, EMOJI_SM_SZ), Image.LANCZOS)
            EMOJI_IMAGES_SM[color_name] = ImageTk.PhotoImage(sm)

            card = full.resize((CARD_ICON_SIZE, CARD_ICON_SIZE), Image.LANCZOS)
            EMOJI_IMAGES_CARD[color_name] = ImageTk.PhotoImage(card)
        except Exception as e:
            print(f"Could not load emoji icon {svg_path.name}: {e}")


DEVICE_CARD_COLOR = {
    singleMotor: "#2a7d8c",   # teal
    doubleMotor: "#2a7d8c",   # teal
    colorSensor: "#c0392b",   # light red
    controller:  "#c0392b",   # light red
}

CARD_WIDTH = 220   # fixed width for all DeviceCards


# ── Utilities ─────────────────────────────────────────────────────────────────

def _draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Draw a filled rounded rectangle on a Canvas."""
    canvas.create_polygon(
        x1 + r, y1,   x2 - r, y1,
        x2,     y1,   x2,     y1 + r,
        x2,     y2 - r, x2,   y2,
        x2 - r, y2,   x1 + r, y2,
        x1,     y2,   x1,     y2 - r,
        x1,     y1 + r, x1,   y1,
        smooth=True, **kw,
    )


class RoundedPanel(tk.Frame):
    """A Frame with a rounded-rectangle Canvas backdrop."""
    def __init__(self, parent, radius=RADIUS, fill=BG2, outline=BORDER, **kw):
        super().__init__(parent, bg=parent["bg"], **kw)
        self._radius  = radius
        self._fill    = fill
        self._outline = outline
        self._canvas  = tk.Canvas(self, bg=parent["bg"], bd=0, highlightthickness=0)
        self._canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _=None):
        self._canvas.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        r = self._radius
        _draw_rounded_rect(self._canvas, 1, 1, w - 1, h - 1, r,
                           fill=self._fill, outline=self._outline)
        self._canvas.lower("all")


def btn(parent, text, command, bg=ACCENT, fg="black", font_size=12, pad=(14, 8)):
    b = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
        relief="flat", bd=0, cursor="hand2",
        padx=pad[0], pady=pad[1],
        font=(FONT, font_size, "bold"),
        highlightthickness=0,
    )
    return b


def lbl(parent, text="", fg=FG, size=11, bold=False, anchor="w", **kw):
    return tk.Label(
        parent, text=text, fg=fg, bg=parent["bg"],
        font=(FONT, size, "bold" if bold else "normal"),
        anchor=anchor, **kw,
    )


# ── Device icon widget ────────────────────────────────────────────────────────

ICON_W      = 130   # full card width  (unused in compact bar)
ICON_H      = 120   # full card height (unused in compact bar)
ICON_W_SM    = 72    # compact icon canvas width
ICON_H_SM    = 64    # compact icon canvas height
ICON_COL_W   = 80    # total column width for compact DeviceIcon widget
EMOJI_SM_SZ  = 32    # emoji icon size in scan strip (half of icon canvas ~)
RING_W  = 3     # border thickness
SEL_W   = 3     # extra selection border
BAR_H   = 170   # top strip height — fits icon + emoji + serial + mac + type

class DeviceIcon(tk.Frame):
    """Clickable icon for a scanned device. compact=True omits text labels."""

    def __init__(self, parent, result: ScanResult, on_toggle, compact: bool = False):
        bg = BG2
        super().__init__(parent, bg=bg, cursor="hand2")
        self._result    = result
        self._on_toggle = on_toggle
        self._selected  = False
        self._compact   = compact
        self._build()
        self.bind_all_children("<Button-1>", self._click)

    def bind_all_children(self, seq, func):
        self.bind(seq, func)
        for child in self.winfo_children():
            child.bind(seq, func)

    def _build(self):
        color       = self._result.color_hex
        device_type = self._result.device_type
        w = ICON_W_SM if self._compact else ICON_W
        h = ICON_H_SM if self._compact else ICON_H
        pad = (4, 3) if self._compact else (8, 6)

        self._canvas = tk.Canvas(
            self, width=w, height=h,
            bg=BG2, bd=0, highlightthickness=0,
        )
        self._canvas.pack(pady=pad, anchor="center")

        self._rect_id = self._canvas.create_rectangle(
            RING_W, RING_W, w - RING_W, h - RING_W,
            outline=color, width=RING_W, fill=color,
        )

        img = (DEVICE_IMAGES_SM if self._compact else DEVICE_IMAGES).get(device_type)
        if img:
            self._img_id = self._canvas.create_image(
                w // 2, h // 2, image=img, anchor="center",
            )

        else:
            glyph = DEVICE_ICON.get(device_type, '?')
            self._img_id = self._canvas.create_text(
                w // 2, h // 2, text=glyph,
                fill="white", font=(FONT, 18 if self._compact else 28, "bold"),
            )

        if self._compact:
            serial_text = str(self._result.card_serial) if self._result.card_serial else "—"
            mac_short   = self._result.mac[-8:] if self._result.mac else "??"

            # Fixed-height emoji slot — always same size so all icons align
            emoji_slot = tk.Frame(self, bg=BG2, width=EMOJI_SM_SZ, height=EMOJI_SM_SZ)
            emoji_slot.pack_propagate(False)
            emoji_slot.pack(pady=(2, 0))
            em_img_sm = EMOJI_IMAGES_SM.get(self._result.card_color_name)
            if em_img_sm:
                em_lbl = tk.Label(emoji_slot, image=em_img_sm, bg=BG2)
                em_lbl.image = em_img_sm
                em_lbl.place(relx=0.5, rely=0.5, anchor="center")

            tk.Label(self, text=serial_text, bg=BG2, fg=FG,
                     font=(FONT, 9, "bold")).pack()
            tk.Label(self, text=mac_short, bg=BG2, fg=FG_DIM,
                     font=(FONT_MONO, 8)).pack()
            tk.Label(self, text=device_type, bg=BG2, fg=FG,
                     font=(FONT, 8, "bold")).pack(pady=(0, 2))
        else:
            serial_text = str(self._result.card_serial) if self._result.card_serial else "—"
            lbl(self, serial_text, fg=FG, size=13, bold=True,
                anchor="center").pack(fill="x", padx=6)
            mac_short = self._result.mac[-8:] if self._result.mac else "??"
            lbl(self, mac_short, fg=FG_DIM, size=11,
                anchor="center").pack(fill="x", padx=6, pady=(0, 4))
            lbl(self, device_type, fg=FG, size=11, bold=True,
                anchor="center").pack(fill="x", padx=6, pady=(0, 10))

        self.bind_all_children("<Button-1>", self._click)

    def _click(self, _=None):
        self._selected = not self._selected
        self._draw_state()
        self._on_toggle(self._result, self._selected)

    def _draw_state(self):
        color = self._result.color_hex
        if self._selected:
            self._canvas.itemconfig(self._rect_id, outline=FG,
                                    width=RING_W + SEL_W, fill=color)
        else:
            self._canvas.itemconfig(self._rect_id, outline=color,
                                    width=RING_W, fill=color)

    def deselect(self):
        self._selected = False
        self._draw_state()

    @property
    def selected(self):
        return self._selected

    @property
    def result(self):
        return self._result


# ── Device card (post-connect) ────────────────────────────────────────────────

class DeviceCard(tk.Frame):

    def __init__(self, parent, label, dev, scan_result, on_disconnect):
        super().__init__(parent, bg=BG, highlightthickness=0)
        self._label       = label
        self._dev         = dev
        self._result      = scan_result
        self._on_dis      = on_disconnect
        self._tele        = {}
        self._build()

    def _build(self):
        accent = DEVICE_CARD_COLOR.get(type(self._dev), ACCENT)

        panel = RoundedPanel(self, radius=RADIUS, fill=BG2, outline=BORDER)
        panel.pack(fill="both", expand=True)

        # invisible spacer that enforces consistent card width without pack_propagate
        tk.Frame(panel, bg=BG2, width=CARD_WIDTH, height=1).pack()

        # header
        hdr = tk.Frame(panel, bg=accent)
        hdr.pack(fill="x")
        tk.Label(hdr, text=self._label, bg=accent, fg="white",
                 font=(FONT, 12, "bold"), padx=10, pady=7).pack(side="left")
        tk.Button(hdr, text="X", command=lambda: self._on_dis(self._label),
                  bg=accent, fg="black", activebackground=DANGER,
                  relief="flat", bd=0, padx=10, pady=7,
                  font=(FONT, 13, "bold"), cursor="hand2",
                  highlightthickness=0).pack(side="right")

        # device icon + emoji + serial — centred column
        banner = tk.Frame(panel, bg=BG2)
        banner.pack(fill="x", padx=8, pady=(6, 2))

        device_type = self._result.device_type if self._result else None
        dev_img = DEVICE_IMAGES.get(device_type) if device_type else None
        if dev_img:
            icon_lbl = tk.Label(banner, image=dev_img, bg=BG2)
            icon_lbl.image = dev_img
            icon_lbl.pack()

        if self._result:
            serial = str(self._result.card_serial) if self._result.card_serial else "—"
            color  = self._result.card_color_name or "unknown"

            em_img = EMOJI_IMAGES_CARD.get(color)
            if em_img:
                em_lbl = tk.Label(banner, image=em_img, bg=BG2)
                em_lbl.image = em_img
                em_lbl.pack(pady=(6, 0))

            tk.Label(banner, text=serial, bg=BG2, fg=FG,
                     font=(FONT, 14, "bold")).pack(pady=(4, 0))
            tk.Label(banner, text=color.capitalize(), bg=BG2, fg=FG_DIM,
                     font=(FONT, 11)).pack()

        # telemetry
        tf = tk.Frame(panel, bg=BG2)
        tf.pack(fill="x", padx=8, pady=4)
        for key in self._tele_keys():
            row = tk.Frame(tf, bg=BG2)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=key, bg=BG2, fg=FG_DIM,
                     font=(FONT, 11), width=10, anchor="w").pack(side="left")
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=BG2, fg=FG,
                     font=(FONT_MONO, 12, "bold")).pack(side="left")
            self._tele[key] = var

        # controls
        self._build_controls(panel)

    def _tele_keys(self):
        if isinstance(self._dev, doubleMotor):
            return ["pos L", "pos R", "speed L", "speed R", "yaw"]
        if isinstance(self._dev, singleMotor):
            return ["position", "speed"]
        if isinstance(self._dev, controller):
            return ["left %", "right %"]
        if isinstance(self._dev, colorSensor):
            return ["color", "reflection"]
        return []

    def _build_controls(self, parent):
        cf = tk.Frame(parent, bg=BG2)
        cf.pack(fill="x", padx=8, pady=(0, 8))

        if isinstance(self._dev, (singleMotor, doubleMotor)):
            self._spd = tk.IntVar(value=50)
            sr = tk.Frame(cf, bg=BG2)
            sr.pack(fill="x", pady=(0, 4))
            tk.Label(sr, text="spd", bg=BG2, fg=FG_DIM,
                     font=(FONT, 10), anchor="w").pack(side="left")
            tk.Scale(sr, from_=-100, to=100, orient="horizontal",
                     variable=self._spd, bg=BG2, fg=FG,
                     troughcolor=BG3, highlightthickness=0,
                     activebackground=ACCENT, length=120,
                     showvalue=False).pack(side="left", fill="x", expand=True)

            br = tk.Frame(cf, bg=BG2)
            br.pack(fill="x")
            btn(br, "Run", self._run, bg=SUCCESS, font_size=9,
                pad=(8, 3)).pack(side="left", padx=(0, 3))
            btn(br, "Stop", self._stop, bg=DANGER, font_size=9,
                pad=(8, 3)).pack(side="left")
            if isinstance(self._dev, doubleMotor):
                btn(br, "Reset yaw", self._reset_heading,
                    bg=BG3, fg="black", font_size=9,
                    pad=(8, 3)).pack(side="left", padx=(3, 0))
        else:
            tk.Label(cf, text="Read-only", bg=BG2, fg=FG_DIM,
                     font=(FONT, 10)).pack(anchor="w")

        # Beep button — all device types
        btn(cf, "Beep", self._beep, bg=BG3, fg=FG, font_size=9,
            pad=(8, 3)).pack(fill="x", pady=(6, 0))

    def _run(self):
        try: self._dev.run(self._spd.get())
        except Exception as e: print("run error:", e)

    def _stop(self):
        try: self._dev.stop()
        except Exception as e: print("stop error:", e)

    def _reset_heading(self):
        try: self._dev.reset_heading()
        except Exception as e: print("reset error:", e)

    def _beep(self):
        threading.Thread(target=self._dev.beep, daemon=True).start()

    def update_telemetry(self, values):
        mapping = {
            "position": "position", "speed": "speed",
            "pos L": "pos_L", "pos R": "pos_R",
            "speed L": "speed_L", "speed R": "speed_R",
            "yaw": "yaw", "left %": "left", "right %": "right",
            "color": "color", "reflection": "reflection",
        }
        for ui_key, data_key in mapping.items():
            if ui_key in self._tele and data_key in values:
                v = values[data_key]
                if v is None:
                    self._tele[ui_key].set("…")
                elif isinstance(v, float):
                    self._tele[ui_key].set(f"{v:.1f}")
                else:
                    self._tele[ui_key].set(str(v))


# ── Behavior UI ───────────────────────────────────────────────────────────────

# Color int (from legoeducation) → behavior index (0-based): index = color_int - 1
# 1=Red 2=Yellow 3=Blue 4=Teal 5=Green 6=Purple 7=White 8=Magenta 9=Orange 10=Azure
_CARD_COLOR_NAMES = {
    1: ('Red',     '#de1a21'),
    2: ('Yellow',  '#ffd400'),
    3: ('Blue',    '#006cb8'),
    4: ('Teal',    '#1de9b6'),
    5: ('Green',   '#61a836'),
    6: ('Purple',  '#4b2f91'),
    7: ('White',   '#f5f5f5'),
    8: ('Magenta', '#e4599e'),
    9: ('Orange',  '#f57d20'),
    10:('Azure',   '#78bfea'),
}

CARD_POLL_MS = 80   # how often to check for card taps


def _behavior_available(mod, devices: dict) -> bool:
    """True if all required device types are present in devices."""
    return all(
        any(isinstance(d, cls) for d in devices.values())
        for cls in mod.REQUIRED
    )


class BehaviorCard(tk.Frame):
    """One clickable tile representing a single behavior."""

    _ACTIVE_BG   = "#1e4f82"
    _ACTIVE_FG   = "white"
    _INACTIVE_BG = BG2
    _INACTIVE_FG = FG
    _UNAVAIL_BG  = BG3
    _UNAVAIL_FG  = FG_DIM

    def __init__(self, parent, mod, index, on_click):
        super().__init__(parent, bg=BG2, cursor="hand2",
                         highlightthickness=2, highlightbackground=BORDER)
        self._mod      = mod
        self._index    = index
        self._on_click = on_click
        self._active   = False
        self._avail    = True
        self._build()
        self.bind("<Button-1>", self._click)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._click)

    def _build(self):
        # fixed width spacer
        tk.Frame(self, bg=BG2, width=200, height=1).pack()

        tk.Label(self, text=self._mod.NAME, bg=BG2, fg=FG,
                 font=(FONT, 13, "bold"), wraplength=180,
                 anchor="w", justify="left").pack(fill="x", padx=10, pady=(8, 2))

        tk.Label(self, text=self._mod.DESCRIPTION, bg=BG2, fg=FG_DIM,
                 font=(FONT, 10), wraplength=180,
                 anchor="w", justify="left").pack(fill="x", padx=10)

        # required device chips
        chips = tk.Frame(self, bg=BG2)
        chips.pack(fill="x", padx=10, pady=(6, 4))
        for cls in self._mod.REQUIRED:
            pretty = {
                "singleMotor": "Single Motor",
                "doubleMotor": "Double Motor",
                "colorSensor": "Color Sensor",
                "controller":  "Controller",
            }.get(cls.__name__, cls.__name__)
            tk.Label(chips, text=pretty, bg=BG3, fg=FG_DIM,
                     font=(FONT, 9), padx=5, pady=2,
                     relief="flat").pack(side="left", padx=(0, 4))

        # card trigger chip — color int = behavior index + 1
        card_info = _CARD_COLOR_NAMES.get(self._index + 1)
        if card_info:
            color_name, hex_col = card_info
            trigger = tk.Frame(self, bg=BG2)
            trigger.pack(fill="x", padx=10, pady=(2, 8))
            tk.Frame(trigger, bg=hex_col, width=12, height=12).pack(
                side="left", padx=(0, 5))
            tk.Label(trigger, text=f"{color_name} card", bg=BG2, fg=FG_DIM,
                     font=(FONT, 9)).pack(side="left")

    def _click(self, _=None):
        if self._avail:
            self._on_click(self._mod)

    def set_active(self, active: bool):
        self._active = active
        self._refresh_style()

    def set_available(self, avail: bool):
        self._avail = avail
        self.config(cursor="hand2" if avail else "arrow")
        self._refresh_style()

    def _refresh_style(self):
        if self._active:
            bg, fg, border = self._ACTIVE_BG, self._ACTIVE_FG, FG
        elif not self._avail:
            bg, fg, border = self._UNAVAIL_BG, self._UNAVAIL_FG, BORDER
        else:
            bg, fg, border = self._INACTIVE_BG, self._INACTIVE_FG, BORDER

        self.config(bg=bg, highlightbackground=border)
        for w in self.winfo_children():
            try:
                w.config(bg=bg, fg=fg)
                for ww in w.winfo_children():
                    ww.config(bg=bg, fg=FG_DIM if not self._active else "white")
            except tk.TclError:
                pass


class BehaviorPanel(tk.Frame):
    """Scrollable (paged) panel of behavior tiles at the bottom of the window."""

    PER_PAGE = 4

    def __init__(self, parent, behaviors: list, get_devices):
        super().__init__(parent, bg=BG)
        self._behaviors   = behaviors
        self._get_devices = get_devices
        self._page        = 0
        self._active_mod  = None
        self._cards: list[BehaviorCard] = []
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=40, pady=(8, 4))

        tk.Label(hdr, text="Behaviors", bg=BG, fg=FG,
                 font=(FONT, 14, "bold")).pack(side="left")

        self._page_lbl = tk.Label(hdr, text="", bg=BG, fg=FG_DIM,
                                  font=(FONT, 11))
        self._page_lbl.pack(side="left", padx=12)

        btn(hdr, ">", lambda: self._turn_page(1),
            bg=BG3, fg=FG, font_size=11, pad=(10, 2)).pack(side="right")
        btn(hdr, "<", lambda: self._turn_page(-1),
            bg=BG3, fg=FG, font_size=11, pad=(10, 2)).pack(side="right", padx=(0, 4))

        self._card_row = tk.Frame(self, bg=BG)
        self._card_row.pack(fill="x", padx=40, pady=(0, 16))

        self._render_page()

    def _n_pages(self):
        return max(1, -(-len(self._behaviors) // self.PER_PAGE))  # ceiling div

    def _turn_page(self, delta):
        self._page = (self._page + delta) % self._n_pages()
        self._render_page()

    def _render_page(self):
        for c in self._cards:
            c.destroy()
        self._cards.clear()

        devices = self._get_devices()
        start   = self._page * self.PER_PAGE
        page    = self._behaviors[start: start + self.PER_PAGE]

        for i, mod in enumerate(page):
            global_index = start + i
            card = BehaviorCard(self._card_row, mod, global_index, self._on_card_click)
            card.pack(side="left", padx=(0, 10), pady=4, fill="y")
            card.set_available(_behavior_available(mod, devices))
            card.set_active(mod is self._active_mod)
            self._cards.append(card)

        self._page_lbl.config(
            text=f"page {self._page + 1} / {self._n_pages()}"
        )

    def _on_card_click(self, mod):
        if self._active_mod is mod:
            mod.stop()
            self._active_mod = None
        else:
            if self._active_mod:
                self._active_mod.stop()
            self._active_mod = mod
            mod.start(self._get_devices())
        self._render_page()

    def activate_by_index(self, index: int):
        """Activate the behavior at the given 0-based index (from a card tap).
        Tapping the same card again deactivates the current behavior."""
        if index < 0 or index >= len(self._behaviors):
            return
        mod = self._behaviors[index]
        if not _behavior_available(mod, self._get_devices()):
            return
        # jump to the page containing this behavior
        self._page = index // self.PER_PAGE
        self._on_card_click(mod)

    def refresh(self):
        """Call after devices connect/disconnect to update availability and stop
        any active behavior whose required devices are no longer present."""
        if self._active_mod and not _behavior_available(
                self._active_mod, self._get_devices()):
            self._active_mod.stop()
            self._active_mod = None
        self._render_page()


# ── Main application ──────────────────────────────────────────────────────────

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("noWand")
        self.configure(bg=BG)
        self.state("zoomed")           # full-screen (macOS maximised)

        load_device_icons()
        load_emoji_icons()
        self._manager    = DeviceManager()
        self._scan_results: list[ScanResult] = []
        self._selected:  set  = set()  # ScanResult objects currently selected
        self._icons:     list = []     # DeviceIcon widgets
        self._cards:     dict = {}     # label -> DeviceCard
        self._scanning   = False
        self._has_scanned = False
        self._behaviors  = _behavior_pkg.load_all()

        # Filter state
        self._filter_color      = tk.StringVar(value="")
        self._filter_serial     = tk.StringVar(value="")
        self._filter_color_var  = tk.StringVar(value="Any")
        self._filter_serial_var = tk.StringVar(value="")
        self._filter_panel_visible = False
        self._filter_frame = None   # filter panel removed from layout

        self._build()
        self.after(POLL_MS, self._poll_telemetry)
        self.after(CARD_POLL_MS, self._poll_cards)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── style ──
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TCombobox",
                         fieldbackground=BG3, background=BG3,
                         foreground=FG, selectbackground=ACCENT,
                         selectforeground="white", borderwidth=0,
                         relief="flat")
        style.configure("TScrollbar", background=BG3, troughcolor=BG2,
                         borderwidth=0, arrowcolor=FG_DIM)

        # ══════════════════════════════════════════════════════════════════
        # TOP STRIP  — SCAN button left | device icons fill rest of width
        # Height is capped at BAR_H px (≈10% of a typical 900px screen).
        # ══════════════════════════════════════════════════════════════════
        top_strip = tk.Frame(self, bg=BG2, height=BAR_H)
        top_strip.pack(fill="x", side="top")
        top_strip.pack_propagate(False)   # lock height

        # ── Left input panel: color dropdown + card number stacked ──
        input_panel = tk.Frame(top_strip, bg=BG2)
        input_panel.pack(side="left", padx=(12, 4), pady=10, fill="y")

        colors = ["Any color"] + list(COLOR_MAP.keys())
        self._color_var = tk.StringVar(value="Any color")
        ttk.Combobox(input_panel, textvariable=self._color_var,
                     values=colors, state="readonly", width=14,
                     font=(FONT, 11)).pack(fill="x", pady=(0, 4))

        self._serial_entry = tk.Entry(
            input_panel, width=14, bg=BG3, fg=FG_DIM, insertbackground=FG,
            relief="flat", font=(FONT, 11), bd=0,
        )
        self._serial_entry.insert(0, "Card number")
        self._serial_entry.bind("<FocusIn>",  self._serial_focus_in)
        self._serial_entry.bind("<FocusOut>", self._serial_focus_out)
        self._serial_entry.pack(fill="x", ipady=5)

        # SCAN / RESCAN button — next to input panel
        self._scan_btn = btn(top_strip, "SCAN", self._do_scan,
                             bg=ACCENT, font_size=14, pad=(24, 0))
        self._scan_btn.pack(side="left", padx=(4, 8), pady=10, fill="y")

        # Status label tucked right after button
        self._status_var = tk.StringVar(value="")
        tk.Label(top_strip, textvariable=self._status_var, bg=BG2, fg=FG_DIM,
                 font=(FONT, 11), anchor="w").pack(side="left", padx=(0, 4))

        # CONNECT SELECTED — anchored to the right
        self._connect_btn = btn(top_strip, "CONNECT SELECTED", self._do_connect,
                                bg=SUCCESS, fg="black", font_size=12, pad=(16, 0))
        self._connect_btn.pack(side="right", padx=(4, 12), pady=10, fill="y")
        self._connect_btn.config(state="disabled", bg=BG3, fg=FG_DIM, cursor="arrow")

        # Horizontal scrollable icon canvas — fills remaining width
        icon_outer = tk.Frame(top_strip, bg=BG2)
        icon_outer.pack(side="left", fill="both", expand=True, pady=0, padx=(0, 4))

        self._icon_canvas = tk.Canvas(icon_outer, bg=BG2,
                                      height=BAR_H, bd=0, highlightthickness=0)
        hscroll = ttk.Scrollbar(icon_outer, orient="horizontal",
                                 command=self._icon_canvas.xview)
        self._icon_canvas.configure(xscrollcommand=hscroll.set)
        hscroll.pack(side="bottom", fill="x")
        self._icon_canvas.pack(fill="both", expand=True)

        self._icon_row = tk.Frame(self._icon_canvas, bg=BG2)
        self._icon_canvas_window = self._icon_canvas.create_window(
            (0, 0), window=self._icon_row, anchor="nw",
        )
        self._icon_row.bind("<Configure>", self._update_icon_scroll)

        # empty state label
        self._empty_lbl = tk.Label(
            self._icon_row,
            text="Press SCAN to discover nearby LEGO devices",
            bg=BG2, fg=FG_DIM, font=(FONT, 11),
        )
        self._empty_lbl.pack(side="left", padx=16, pady=0, anchor="center")

        # ══════════════════════════════════════════════════════════════════
        # MAIN AREA  — title, controls, connect, cards
        # ══════════════════════════════════════════════════════════════════
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, side="top")

        # ── Connected devices area ──
        sep = tk.Frame(main, bg=BORDER, height=2)
        sep.pack(fill="x", padx=40, pady=(12, 0))

        self._cards_label = tk.Label(main, text="", bg=BG, fg=FG,
                                     font=(FONT, 14, "bold"))
        self._cards_label.pack(anchor="w", padx=48, pady=(10, 0))

        cards_outer = tk.Frame(main, bg=BG)
        cards_outer.pack(fill="both", expand=True, padx=40, pady=(4, 16))

        self._cards_canvas = tk.Canvas(cards_outer, bg=BG, bd=0, highlightthickness=0)
        cards_scroll = ttk.Scrollbar(cards_outer, orient="horizontal",
                                     command=self._cards_canvas.xview)
        self._cards_canvas.configure(xscrollcommand=cards_scroll.set)
        cards_scroll.pack(side="bottom", fill="x")
        self._cards_canvas.pack(fill="both", expand=True)

        self._cards_frame = tk.Frame(self._cards_canvas, bg=BG)
        self._cards_win = self._cards_canvas.create_window(
            (0, 0), window=self._cards_frame, anchor="nw",
        )
        self._cards_frame.bind("<Configure>",
            lambda e: self._cards_canvas.configure(
                scrollregion=self._cards_canvas.bbox("all")))

        # ── Behavior panel ────────────────────────────────────────────────────
        sep2 = tk.Frame(main, bg=BORDER, height=2)
        sep2.pack(fill="x", padx=40, pady=(4, 0))

        self._behavior_panel = BehaviorPanel(
            main,
            self._behaviors,
            get_devices=lambda: self._manager.devices,
        )
        self._behavior_panel.pack(fill="x", side="top")

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _serial_focus_in(self, _):
        if self._serial_entry.get() == "Card number":
            self._serial_entry.delete(0, "end")
            self._serial_entry.config(fg=FG)

    def _serial_focus_out(self, _):
        if not self._serial_entry.get():
            self._serial_entry.insert(0, "Card number")
            self._serial_entry.config(fg=FG_DIM)

    def _do_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._scan_btn.config(text="Scanning…", state="disabled",
                              bg=ACCENT_DIM, cursor="arrow")
        self._clear_icons()
        self._scan_results.clear()
        self._selected.clear()
        self._update_connect_btn()

        color_raw = self._color_var.get()
        color = None if color_raw == "Any color" else color_raw

        serial_raw = self._serial_entry.get().strip()
        serial = None
        if serial_raw and serial_raw != "Card number":
            try:
                serial = int(serial_raw)
            except ValueError:
                pass

        threading.Thread(target=self._scan_worker,
                         args=(serial, color), daemon=True).start()

    def _scan_worker(self, serial, color):
        try:
            results = self._manager.scan(
                card_serial=serial,
                card_color=color,
                on_found=lambda r: self.after(0, self._add_icon, r),
            )
            self._scan_results = results
        except Exception as e:
            self.after(0, lambda: self._set_status(f"Scan error: {e}"))
        finally:
            self.after(0, self._scan_done)

    def _scan_done(self):
        self._scanning = False
        self._has_scanned = True
        self._scan_btn.config(text="RESCAN", state="normal",
                              bg=ACCENT, cursor="hand2")
        count = len(self._scan_results)
        self._set_status(f"Found {count} device{'s' if count != 1 else ''}")
        if count == 0:
            self._empty_lbl.config(text="No devices found — try RESCAN")
            self._empty_lbl.pack()

    # ── Icon management ───────────────────────────────────────────────────────

    def _clear_icons(self):
        for icon in self._icons:
            icon.destroy()
        self._icons.clear()
        self._empty_lbl.config(text="Scanning…")
        self._empty_lbl.pack()

    def _add_icon(self, result: ScanResult):
        if len(self._icons) == 0:
            self._empty_lbl.pack_forget()

        icon = DeviceIcon(self._icon_row, result, self._on_icon_toggle, compact=True)
        icon.pack(side="left", padx=6, pady=4)
        self._icons.append(icon)
        self._icon_row.update_idletasks()
        self._update_icon_scroll()

    def _update_icon_scroll(self, _=None):
        self._icon_canvas.configure(scrollregion=self._icon_canvas.bbox("all"))

    def _on_icon_toggle(self, result: ScanResult, selected: bool):
        if selected:
            self._selected.add(result)
        else:
            self._selected.discard(result)
        self._update_connect_btn()

    def _update_connect_btn(self):
        if self._selected:
            self._connect_btn.config(
                state="normal", cursor="hand2",
                bg=SUCCESS, fg="black",
                text=f"CONNECT  ({len(self._selected)} selected)",
            )
        else:
            self._connect_btn.config(
                state="disabled", cursor="arrow",
                bg=BG2, fg=FG_DIM,
                text="CONNECT SELECTED",
            )

    # ── Filter ────────────────────────────────────────────────────────────────

    def _toggle_filter(self):
        if self._filter_frame is None:
            return
        if self._filter_panel_visible:
            self._filter_frame.pack_forget()
        else:
            self._filter_frame.pack(fill="x", padx=12, pady=(0, 8))
        self._filter_panel_visible = not self._filter_panel_visible

    def _apply_filter(self):
        fc = self._filter_color_var.get()
        fs = self._filter_serial_var.get().strip()
        want_color  = None if fc == "Any" else fc
        want_serial = None
        if fs:
            try: want_serial = int(fs)
            except ValueError: pass

        for icon in self._icons:
            r = icon.result
            show = True
            if want_color and r.card_color_name != want_color:
                show = False
            if want_serial and r.card_serial != want_serial:
                show = False
            if show:
                icon.pack(side="left", padx=10, pady=4)
            else:
                icon.pack_forget()
                self._selected.discard(r)
                icon.deselect()

        self._update_connect_btn()

    # ── Connect ───────────────────────────────────────────────────────────────

    def _do_connect(self):
        if not self._selected:
            return
        to_connect = list(self._selected)
        self._connect_btn.config(state="disabled", text="Connecting…",
                                 cursor="arrow", bg=ACCENT_DIM)
        threading.Thread(target=self._connect_worker,
                         args=(to_connect,), daemon=True).start()

    def _connect_worker(self, results):
        for sr in results:
            ui_done = threading.Event()
            try:
                label, dev = self._manager.connect_one(sr)
                self.after(0, lambda l=label, d=dev, r=sr, ev=ui_done:
                           (self._on_one_connected(r, l, d), ev.set()))
            except Exception as e:
                name = f"{sr.device_type} {sr.card_serial or sr.mac[-5:]}"
                msg  = str(e).splitlines()[-1]
                self.after(0, lambda m=f"Failed to connect {name}: {m}", ev=ui_done:
                           (self._set_status(m), self._update_connect_btn(), ev.set()))
            ui_done.wait()   # block until UI has updated before connecting next device
        self.after(0, self._connect_done)

    def _on_one_connected(self, scan_result, label, dev):
        # Remove this device's icon from the scan list immediately
        remaining = []
        for icon in self._icons:
            if icon.result.mac == scan_result.mac:
                self._selected.discard(icon.result)
                icon.destroy()
            else:
                remaining.append(icon)
        self._icons = remaining
        if not self._icons:
            self._empty_lbl.config(text="Press SCAN to discover nearby LEGO devices")
            self._empty_lbl.pack(side="left", padx=16, pady=0, anchor="center")

        if label not in self._cards:
            card = DeviceCard(
                self._cards_frame, label, dev, scan_result,
                on_disconnect=self._disconnect_device,
            )
            card.pack(side="left", fill="y", padx=(0, 8), pady=4)
            self._cards[label] = card

        self._cards_label.config(
            text=f"Connected devices  ({len(self._cards)})"
        )
        self._update_connect_btn()
        self._set_status(f"Connected: {label}")
        self._behavior_panel.refresh()
        self.update_idletasks()   # flush redraws immediately — syncs with BLE beep

    def _connect_done(self):
        n = len(self._cards)
        if n:
            self._set_status(f"{n} device{'s' if n != 1 else ''} connected")
        # Only clear selection for icons that actually connected (already removed from _icons)
        # Icons still in _icons are failed devices — leave them selected so user can retry
        still_present = {icon.result for icon in self._icons}
        self._selected &= still_present
        self._update_connect_btn()

    # ── Device cards ──────────────────────────────────────────────────────────

    def _disconnect_device(self, label):
        self._manager.disconnect(label)
        card = self._cards.pop(label, None)
        if card:
            card.destroy()
        n = len(self._cards)
        self._cards_label.config(
            text=f"Connected devices  ({n})" if n else ""
        )
        self._set_status(
            f"{n} device{'s' if n != 1 else ''} connected" if n else "No devices connected"
        )
        self._behavior_panel.refresh()

    # ── Telemetry poll ────────────────────────────────────────────────────────

    def _poll_telemetry(self):
        snapshot = self._manager.read_all()
        for label, values in snapshot.items():
            if label in self._cards:
                self._cards[label].update_telemetry(values)
        self.after(POLL_MS, self._poll_telemetry)

    def _poll_cards(self):
        for dev in self._manager.devices.values():
            try:
                if dev.card_tapped():
                    color_int = dev.scanned_card.color
                    if color_int and color_int > 0:
                        self._behavior_panel.activate_by_index(color_int - 1)
                    break   # one tap per poll cycle is enough
            except Exception:
                pass
        self.after(CARD_POLL_MS, self._poll_cards)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg):
        self._status_var.set(msg)

    def _on_close(self):
        self._manager.disconnect_all()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
