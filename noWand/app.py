"""
noWand — desktop app.
Run: python app.py
"""

import threading
import tkinter as tk
from tkinter import ttk

from device_manager import DeviceManager, ScanResult, COLOR_MAP, COLOR_HEX
from lelib import singleMotor, doubleMotor, colorSensor, controller

# ── Theme ─────────────────────────────────────────────────────────────────────
BG          = "#0f0f1a"
BG2         = "#1a1a2e"
BG3         = "#252540"
FG          = "#e0e0f0"
FG_DIM      = "#6060a0"
ACCENT      = "#5c7cfa"
ACCENT_DIM  = "#3a4f9e"
SUCCESS     = "#51cf66"
DANGER      = "#ff6b6b"
BORDER      = "#2a2a4a"
SEL_RING    = "#ffffff"

FONT        = "SF Pro Display"
FONT_MONO   = "SF Pro Mono"

POLL_MS     = 100

# Device type icons (unicode glyphs used as placeholder art)
DEVICE_ICON = {
    'Single Motor': '⚙',
    'Double Motor': '⚙⚙',
    'Color Sensor': '◉',
    'Controller':   '⊕',
}

DEVICE_CARD_COLOR = {
    singleMotor: "#7c5cfc",
    doubleMotor: "#5c7cfa",
    colorSensor: "#51cf66",
    controller:  "#f59f00",
}


# ── Utilities ─────────────────────────────────────────────────────────────────

def btn(parent, text, command, bg=ACCENT, fg="white", font_size=12, pad=(14, 8)):
    b = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=fg, activeforeground=bg,
        relief="flat", bd=0, cursor="hand2",
        padx=pad[0], pady=pad[1],
        font=(FONT, font_size, "bold"),
    )
    return b


def lbl(parent, text="", fg=FG, size=11, bold=False, anchor="w", **kw):
    return tk.Label(
        parent, text=text, fg=fg, bg=parent["bg"],
        font=(FONT, size, "bold" if bold else "normal"),
        anchor=anchor, **kw,
    )


# ── Device icon widget ────────────────────────────────────────────────────────

ICON_D  = 90    # canvas diameter
RING_W  = 6     # ring thickness
SEL_W   = 4     # extra selection ring

class DeviceIcon(tk.Frame):
    """Circular icon representing a scanned (not yet connected) device."""

    def __init__(self, parent, result: ScanResult, on_toggle):
        super().__init__(parent, bg=BG2, cursor="hand2")
        self._result    = result
        self._on_toggle = on_toggle
        self._selected  = False
        self._build()
        self.bind_all_children("<Button-1>", self._click)

    def bind_all_children(self, seq, func):
        self.bind(seq, func)
        for child in self.winfo_children():
            child.bind(seq, func)

    def _build(self):
        # ── Canvas circle ──
        self._canvas = tk.Canvas(
            self, width=ICON_D, height=ICON_D,
            bg=BG2, bd=0, highlightthickness=0,
        )
        self._canvas.pack(pady=(10, 4))

        r = ICON_D // 2
        ring = RING_W
        color = self._result.color_hex

        # outer ring
        self._ring_id = self._canvas.create_oval(
            2, 2, ICON_D - 2, ICON_D - 2,
            outline=color, width=ring, fill=BG3,
        )
        # glyph
        glyph = DEVICE_ICON.get(self._result.device_type, '?')
        self._icon_id = self._canvas.create_text(
            r, r, text=glyph,
            fill=color, font=(FONT, 22, "bold"),
        )

        # ── Labels ──
        serial_text = str(self._result.card_serial) if self._result.card_serial else "—"
        lbl(self, serial_text, fg=FG, size=11, bold=True,
            anchor="center").pack(fill="x", padx=6)

        mac_short = self._result.mac[-8:] if self._result.mac else "??"
        lbl(self, mac_short, fg=FG_DIM, size=9,
            anchor="center").pack(fill="x", padx=6, pady=(0, 8))

        lbl(self, self._result.device_type, fg=FG_DIM, size=9,
            anchor="center").pack(fill="x", padx=6, pady=(0, 8))

        self.bind_all_children("<Button-1>", self._click)

    def _click(self, _=None):
        self._selected = not self._selected
        self._draw_state()
        self._on_toggle(self._result, self._selected)

    def _draw_state(self):
        color = self._result.color_hex
        if self._selected:
            self._canvas.itemconfig(self._ring_id, outline=SEL_RING, width=RING_W + SEL_W)
            self._canvas.itemconfig(self._icon_id, fill=SEL_RING)
        else:
            self._canvas.itemconfig(self._ring_id, outline=color, width=RING_W)
            self._canvas.itemconfig(self._icon_id, fill=color)

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

    def __init__(self, parent, label, dev, on_disconnect):
        super().__init__(parent, bg=BG3, highlightthickness=1,
                         highlightbackground=BORDER)
        self._label  = label
        self._dev    = dev
        self._on_dis = on_disconnect
        self._tele   = {}
        self._build()

    def _build(self):
        accent = DEVICE_CARD_COLOR.get(type(self._dev), ACCENT)

        # header
        hdr = tk.Frame(self, bg=accent)
        hdr.pack(fill="x")
        tk.Label(hdr, text=self._label, bg=accent, fg="white",
                 font=(FONT, 12, "bold"), padx=10, pady=6).pack(side="left")
        tk.Button(hdr, text="✕", command=lambda: self._on_dis(self._label),
                  bg=accent, fg="white", activebackground=DANGER,
                  relief="flat", bd=0, padx=8, pady=6,
                  font=(FONT, 11, "bold"), cursor="hand2").pack(side="right")

        # telemetry
        tf = tk.Frame(self, bg=BG3)
        tf.pack(fill="x", padx=10, pady=6)
        for key in self._tele_keys():
            row = tk.Frame(tf, bg=BG3)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=key, bg=BG3, fg=FG_DIM,
                     font=(FONT, 9), width=12, anchor="w").pack(side="left")
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=BG3, fg=FG,
                     font=(FONT_MONO, 10)).pack(side="left")
            self._tele[key] = var

        # controls
        self._build_controls()

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

    def _build_controls(self):
        cf = tk.Frame(self, bg=BG3)
        cf.pack(fill="x", padx=10, pady=(0, 10))

        if isinstance(self._dev, (singleMotor, doubleMotor)):
            self._spd = tk.IntVar(value=50)
            sr = tk.Frame(cf, bg=BG3)
            sr.pack(fill="x", pady=(0, 6))
            tk.Label(sr, text="speed", bg=BG3, fg=FG_DIM,
                     font=(FONT, 9), width=12, anchor="w").pack(side="left")
            tk.Scale(sr, from_=-100, to=100, orient="horizontal",
                     variable=self._spd, bg=BG3, fg=FG,
                     troughcolor=BORDER, highlightthickness=0,
                     activebackground=ACCENT, length=140).pack(side="left")

            br = tk.Frame(cf, bg=BG3)
            br.pack(fill="x")
            btn(br, "Run", self._run, bg=SUCCESS, font_size=10,
                pad=(10, 4)).pack(side="left", padx=(0, 4))
            btn(br, "Stop", self._stop, bg=DANGER, font_size=10,
                pad=(10, 4)).pack(side="left")
            if isinstance(self._dev, doubleMotor):
                btn(br, "Reset heading", self._reset_heading,
                    bg=BG2, font_size=10, pad=(10, 4)).pack(side="left", padx=(4, 0))
        else:
            tk.Label(cf, text="Read-only", bg=BG3, fg=FG_DIM,
                     font=(FONT, 9)).pack(anchor="w")

    def _run(self):
        try: self._dev.run(self._spd.get())
        except Exception as e: print("run error:", e)

    def _stop(self):
        try: self._dev.stop()
        except Exception as e: print("stop error:", e)

    def _reset_heading(self):
        try: self._dev.reset_heading()
        except Exception as e: print("reset error:", e)

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
                self._tele[ui_key].set(f"{v:.1f}" if isinstance(v, float) else str(v))


# ── Main application ──────────────────────────────────────────────────────────

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("noWand")
        self.configure(bg=BG)
        self.state("zoomed")           # full-screen (macOS maximised)

        self._manager    = DeviceManager()
        self._scan_results: list[ScanResult] = []
        self._selected:  set  = set()  # ScanResult objects currently selected
        self._icons:     list = []     # DeviceIcon widgets
        self._cards:     dict = {}     # label -> DeviceCard
        self._scanning   = False
        self._has_scanned = False

        # Filter state
        self._filter_color  = tk.StringVar(value="")
        self._filter_serial = tk.StringVar(value="")
        self._filter_panel_visible = False

        self._build()
        self.after(POLL_MS, self._poll_telemetry)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Title ──
        tk.Label(self, text="noWand", bg=BG, fg=ACCENT,
                 font=(FONT, 28, "bold"), pady=24).pack()

        # ── Scan controls ──
        ctrl = tk.Frame(self, bg=BG)
        ctrl.pack(pady=(0, 16))

        # colour dropdown
        colors = ["Any color"] + list(COLOR_MAP.keys())
        self._color_var = tk.StringVar(value="Any color")
        color_menu = ttk.Combobox(ctrl, textvariable=self._color_var,
                                  values=colors, state="readonly", width=14,
                                  font=(FONT, 12))
        color_menu.pack(side="left", padx=(0, 10))

        # serial entry
        self._serial_entry = tk.Entry(
            ctrl, width=14, bg=BG3, fg=FG, insertbackground=FG,
            relief="flat", font=(FONT, 12), bd=0,
        )
        self._serial_entry.insert(0, "Card number")
        self._serial_entry.config(fg=FG_DIM)
        self._serial_entry.bind("<FocusIn>",  self._serial_focus_in)
        self._serial_entry.bind("<FocusOut>", self._serial_focus_out)
        self._serial_entry.pack(side="left", ipady=6, padx=4)

        # style the combobox to match theme
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TCombobox",
                         fieldbackground=BG3, background=BG3,
                         foreground=FG, selectbackground=ACCENT,
                         selectforeground="white", borderwidth=0)

        # Scan button (centered, below inputs)
        self._scan_btn = btn(self, "SCAN", self._do_scan,
                             bg=ACCENT, font_size=14, pad=(40, 12))
        self._scan_btn.pack(pady=(12, 0))

        self._status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status_var, bg=BG, fg=FG_DIM,
                 font=(FONT, 10)).pack(pady=(6, 0))

        # ── Scan results area ──
        results_outer = tk.Frame(self, bg=BG2,
                                 highlightthickness=1, highlightbackground=BORDER)
        results_outer.pack(fill="x", padx=40, pady=(16, 0))

        # results header row
        rh = tk.Frame(results_outer, bg=BG2)
        rh.pack(fill="x", padx=12, pady=(8, 4))
        self._results_label = tk.Label(rh, text="Scanned devices",
                                       bg=BG2, fg=FG_DIM,
                                       font=(FONT, 10, "bold"))
        self._results_label.pack(side="left")

        filter_btn = tk.Button(rh, text="⊟  Filter", command=self._toggle_filter,
                               bg=BG2, fg=FG_DIM, activebackground=BG3,
                               relief="flat", bd=0, cursor="hand2",
                               font=(FONT, 10))
        filter_btn.pack(side="right")

        # inline filter panel (hidden by default)
        self._filter_frame = tk.Frame(results_outer, bg=BG3)
        fp = self._filter_frame
        tk.Label(fp, text="Filter color:", bg=BG3, fg=FG_DIM,
                 font=(FONT, 10)).pack(side="left", padx=(12, 4))
        filter_colors = ["Any"] + list(COLOR_MAP.keys())
        self._filter_color_var = tk.StringVar(value="Any")
        ttk.Combobox(fp, textvariable=self._filter_color_var,
                     values=filter_colors, state="readonly",
                     width=12, font=(FONT, 10)).pack(side="left", padx=(0, 12))
        tk.Label(fp, text="Serial:", bg=BG3, fg=FG_DIM,
                 font=(FONT, 10)).pack(side="left", padx=(0, 4))
        self._filter_serial_var = tk.StringVar()
        tk.Entry(fp, textvariable=self._filter_serial_var,
                 width=10, bg=BG2, fg=FG, insertbackground=FG,
                 relief="flat", font=(FONT, 10)).pack(side="left", padx=(0, 12), ipady=4)
        btn(fp, "Apply", self._apply_filter, bg=ACCENT,
            font_size=9, pad=(10, 4)).pack(side="left")
        self._filter_frame.pack_forget()

        # horizontal scrollable icon row
        icon_canvas_frame = tk.Frame(results_outer, bg=BG2)
        icon_canvas_frame.pack(fill="x", padx=12, pady=8)

        self._icon_canvas = tk.Canvas(icon_canvas_frame, bg=BG2,
                                      height=190, bd=0, highlightthickness=0)
        hscroll = ttk.Scrollbar(icon_canvas_frame, orient="horizontal",
                                 command=self._icon_canvas.xview)
        self._icon_canvas.configure(xscrollcommand=hscroll.set)
        hscroll.pack(side="bottom", fill="x")
        self._icon_canvas.pack(fill="x")

        self._icon_row = tk.Frame(self._icon_canvas, bg=BG2)
        self._icon_canvas_window = self._icon_canvas.create_window(
            (0, 0), window=self._icon_row, anchor="nw"
        )
        self._icon_row.bind("<Configure>", self._update_icon_scroll)

        # empty state label
        self._empty_lbl = tk.Label(
            self._icon_row, text="Press SCAN to discover nearby LEGO devices",
            bg=BG2, fg=FG_DIM, font=(FONT, 11), pady=60,
        )
        self._empty_lbl.pack()

        # ── Connect button ──
        self._connect_btn = btn(self, "CONNECT SELECTED", self._do_connect,
                                bg=SUCCESS, fg="black", font_size=14, pad=(40, 12))
        self._connect_btn.pack(pady=16)
        self._connect_btn.config(state="disabled",
                                 bg=BG3, fg=FG_DIM, cursor="arrow")

        # ── Connected devices area ──
        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x", padx=40)

        self._cards_label = tk.Label(self, text="", bg=BG, fg=FG_DIM,
                                     font=(FONT, 10, "bold"))
        self._cards_label.pack(anchor="w", padx=40, pady=(8, 0))

        cards_outer = tk.Frame(self, bg=BG)
        cards_outer.pack(fill="both", expand=True, padx=40, pady=(4, 16))

        self._cards_canvas = tk.Canvas(cards_outer, bg=BG, bd=0, highlightthickness=0)
        cards_scroll = ttk.Scrollbar(cards_outer, orient="vertical",
                                     command=self._cards_canvas.yview)
        self._cards_canvas.configure(yscrollcommand=cards_scroll.set)
        cards_scroll.pack(side="right", fill="y")
        self._cards_canvas.pack(side="left", fill="both", expand=True)

        self._cards_frame = tk.Frame(self._cards_canvas, bg=BG)
        self._cards_win = self._cards_canvas.create_window(
            (0, 0), window=self._cards_frame, anchor="nw"
        )
        self._cards_frame.bind("<Configure>",
            lambda e: self._cards_canvas.configure(
                scrollregion=self._cards_canvas.bbox("all")))
        self._cards_canvas.bind("<Configure>",
            lambda e: self._cards_canvas.itemconfig(self._cards_win, width=e.width))

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

        icon = DeviceIcon(self._icon_row, result, self._on_icon_toggle)
        icon.pack(side="left", padx=10, pady=4)
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
                bg=BG3, fg=FG_DIM,
                text="CONNECT SELECTED",
            )

    # ── Filter ────────────────────────────────────────────────────────────────

    def _toggle_filter(self):
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
        try:
            connected = self._manager.connect_results(results)
            self.after(0, lambda: self._on_connected(connected))
        except Exception as e:
            self.after(0, lambda: self._set_status(f"Connect error: {e}"))
            self.after(0, self._update_connect_btn)

    def _on_connected(self, connected):
        for label, dev in connected:
            if label not in self._cards:
                card = DeviceCard(
                    self._cards_frame, label, dev,
                    on_disconnect=self._disconnect_device,
                )
                card.pack(fill="x", pady=(0, 8))
                self._cards[label] = card

        self._cards_label.config(
            text=f"Connected devices  ({len(self._cards)})"
        )
        # Deselect all icons — they are now connected
        for icon in self._icons:
            icon.deselect()
        self._selected.clear()
        self._update_connect_btn()
        self._set_status(f"{len(connected)} device(s) connected")

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

    # ── Telemetry poll ────────────────────────────────────────────────────────

    def _poll_telemetry(self):
        snapshot = self._manager.read_all()
        for label, values in snapshot.items():
            if label in self._cards:
                self._cards[label].update_telemetry(values)
        self.after(POLL_MS, self._poll_telemetry)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg):
        self._status_var.set(msg)

    def _on_close(self):
        self._manager.disconnect_all()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
