"""
main.py — noWand (PyScript edition) application logic.

Builds the UI in the DOM, drives Web Bluetooth connections, streams telemetry,
and runs card-selectable behaviors — all in the browser, no install.
"""
import asyncio

from js import document, setInterval, console
from pyodide.ffi import create_proxy

import lego_ble as L
import ble
import behaviors as behavior_pkg

# keep proxies alive
_proxies = []

TELEMETRY_MS = 120
BEHAVIOR_MS = 60
BEHAVIORS_PER_PAGE = 4


# ── small DOM helpers ────────────────────────────────────────────────────────

def el(tag, cls=None, text=None, html=None, **attrs):
    e = document.createElement(tag)
    if cls:
        e.className = cls
    if text is not None:
        e.textContent = text
    if html is not None:
        e.innerHTML = html
    for k, v in attrs.items():
        e.setAttribute(k.replace("_", "-"), str(v))
    return e


def on(element, event, fn):
    p = create_proxy(fn)
    _proxies.append(p)
    element.addEventListener(event, p)
    return p


def byid(i):
    return document.getElementById(i)


# ── telemetry field definitions per kind ────────────────────────────────────

TELE_FIELDS = {
    L.KIND_SINGLE: [("Position", "position"), ("Speed", "speed")],
    L.KIND_DOUBLE: [("Pos L", "pos_l"), ("Pos R", "pos_r"),
                    ("Speed L", "speed_l"), ("Speed R", "speed_r"), ("Yaw", "yaw")],
    L.KIND_CONTROLLER: [("Left %", "left"), ("Right %", "right")],
    L.KIND_COLOR: [("Color", "color_name"), ("Reflection", "reflection")],
}


class App:
    def __init__(self):
        self.devices = {}        # label -> {dev, card_el, tele:{key:el}}
        self.behaviors = behavior_pkg.load_all()
        self.active_behavior = None   # module or None
        self.behavior_cards = []      # list of {mod, el, index}
        self.page = 0

    # ── lifecycle ──
    def start(self):
        self._render_behaviors()
        self._update_empty_state()

        add_btn = byid("add-device")
        on(add_btn, "click", lambda e: asyncio.ensure_future(self._add_device()))

        prev = byid("beh-prev")
        nxt = byid("beh-next")
        on(prev, "click", lambda e: self._turn_page(-1))
        on(nxt, "click", lambda e: self._turn_page(1))

        if not ble.is_available():
            self._set_status("Web Bluetooth not available — use Chrome or Edge over https or localhost.", warn=True)
            add_btn.setAttribute("disabled", "true")
        else:
            self._set_status("Ready. Click “Add device” to connect LEGO hardware.")

        # periodic loops
        _proxies.append(create_proxy(self._telemetry_tick))
        setInterval(_proxies[-1], TELEMETRY_MS)
        _proxies.append(create_proxy(self._behavior_tick))
        setInterval(_proxies[-1], BEHAVIOR_MS)

    # ── status helper ──
    def _set_status(self, msg, warn=False):
        s = byid("status")
        s.textContent = msg
        s.className = "status warn" if warn else "status"

    def _update_empty_state(self):
        byid("devices-empty").style.display = "none" if self.devices else "block"

    # ── connect ──
    async def _add_device(self):
        try:
            self._set_status("Opening device chooser…")
            handle = None

            dev_holder = {}

            def on_packet(data):
                self._on_packet(dev_holder, data)

            def on_disconnect():
                d = dev_holder.get("dev")
                if d:
                    self._remove_device(d.label)

            handle = await ble.connect(on_packet, on_disconnect)

            kind = L.kind_from_name(handle.name) or L.KIND_SINGLE
            label = self._unique_label(L.KIND_LABEL.get(kind, "Device"))
            dev = L.LegoDevice(kind, label, handle.send)
            dev.handle = handle
            dev_holder["dev"] = dev

            self._add_card(dev)
            dev.request_notifications(50)
            self._set_status(f"Connected: {label}")
        except Exception as e:
            # user cancelling the chooser also lands here
            msg = str(e)
            if "cancelled" in msg.lower() or "user" in msg.lower():
                self._set_status("Connection cancelled.")
            else:
                self._set_status(f"Connect failed: {msg}", warn=True)
                console.log("connect error:", repr(e))

    def _unique_label(self, base):
        if base not in self.devices:
            return base
        i = 2
        while f"{base} {i}" in self.devices:
            i += 1
        return f"{base} {i}"

    # ── incoming packets ──
    def _on_packet(self, dev_holder, data):
        dev = dev_holder.get("dev")
        if not dev:
            return
        subs = L.parse_notification(data)
        if not subs:
            return
        dev.apply(subs)
        serial = dev.card_tapped()
        if serial:
            self._activate_by_card_color(dev.card_color)

    # ── device card UI ──
    def _add_card(self, dev):
        card = el("div", "device-card enter")
        kind = dev.kind

        header = el("div", "device-header")
        header.appendChild(el("span", "device-title", text=dev.label))
        close = el("button", "device-close", text="✕", title="Disconnect")
        on(close, "click", lambda e, lbl=dev.label: self._disconnect(lbl))
        header.appendChild(close)
        card.appendChild(header)

        # icon + card info banner
        banner = el("div", "device-banner")
        icon = el("img", "device-icon", src=f"icons/{kind}.svg", alt=L.KIND_LABEL.get(kind, ""))
        banner.appendChild(icon)
        info = el("div", "device-info")
        emoji_el = el("div", "card-emoji")
        serial_el = el("div", "card-serial", text="—")
        colorname_el = el("div", "card-colorname", text="")
        info.appendChild(emoji_el)
        info.appendChild(serial_el)
        info.appendChild(colorname_el)
        banner.appendChild(info)
        card.appendChild(banner)

        # telemetry rows
        tele_wrap = el("div", "tele")
        tele = {}
        for label, key in TELE_FIELDS.get(kind, []):
            row = el("div", "tele-row")
            row.appendChild(el("span", "tele-key", text=label))
            val = el("span", "tele-val", text="…")
            row.appendChild(val)
            tele_wrap.appendChild(row)
            tele[key] = val
        card.appendChild(tele_wrap)

        # controls
        controls = el("div", "controls")
        if kind in (L.KIND_SINGLE, L.KIND_DOUBLE):
            slider = el("input", "speed-slider", type="range", min="-100", max="100", value="50")
            speed_state = {"v": 50}
            on(slider, "input", lambda e, st=speed_state, s=slider: st.__setitem__("v", int(s.value)))
            controls.appendChild(slider)

            btn_row = el("div", "btn-row")
            run = el("button", "btn run", text="Run")
            stop = el("button", "btn stop", text="Stop")
            on(run, "click", lambda e, d=dev, st=speed_state: d.run(st["v"]))
            on(stop, "click", lambda e, d=dev: d.stop())
            btn_row.appendChild(run)
            btn_row.appendChild(stop)
            controls.appendChild(btn_row)
        else:
            controls.appendChild(el("div", "readonly", text="Read-only sensor"))

        beep = el("button", "btn beep", text="Beep")
        on(beep, "click", lambda e, d=dev: d.beep())
        controls.appendChild(beep)
        card.appendChild(controls)

        byid("devices").appendChild(card)
        self.devices[dev.label] = {
            "dev": dev, "card_el": card, "tele": tele,
            "emoji": emoji_el, "serial": serial_el, "colorname": colorname_el,
        }
        self._update_empty_state()
        self._refresh_behavior_availability()

    def _disconnect(self, label):
        entry = self.devices.get(label)
        if entry and entry["dev"].handle:
            asyncio.ensure_future(entry["dev"].handle.disconnect())
        self._remove_device(label)

    def _remove_device(self, label):
        entry = self.devices.pop(label, None)
        if not entry:
            return
        entry["card_el"].remove()
        self._update_empty_state()
        # stop active behavior if it now lacks a required device
        if self.active_behavior and not self._available(self.active_behavior):
            self._deactivate()
        self._refresh_behavior_availability()
        n = len(self.devices)
        self._set_status(f"{n} device{'s' if n != 1 else ''} connected" if n else "No devices connected")

    # ── telemetry refresh ──
    def _telemetry_tick(self, *_):
        for entry in self.devices.values():
            dev = entry["dev"]
            for key, valel in entry["tele"].items():
                v = getattr(dev, key, None)
                valel.textContent = self._fmt(v)
            # card emoji + serial
            if dev.card_serial:
                entry["serial"].textContent = str(dev.card_serial)
                name = L.COLOR_INFO.get(dev.card_color, ("", ""))[0]
                entry["colorname"].textContent = name
                emoji_name = L.COLOR_EMOJI.get(dev.card_color)
                if emoji_name:
                    entry["emoji"].innerHTML = (
                        f'<img class="emoji-img" src="icons/emoji/{emoji_name}.svg" alt="{name}">'
                    )

    @staticmethod
    def _fmt(v):
        if v is None:
            return "…"
        if isinstance(v, float):
            return f"{v:.1f}"
        return str(v)

    # ── behaviors ──
    def _available(self, mod):
        kinds = [e["dev"].kind for e in self.devices.values()]
        return all(req in kinds for req in mod.REQUIRED)

    def _render_behaviors(self):
        row = byid("behaviors")
        row.innerHTML = ""
        self.behavior_cards = []
        for i, mod in enumerate(self.behaviors):
            card = el("div", "behavior-card")
            card.appendChild(el("div", "behavior-name", text=mod.NAME))
            card.appendChild(el("div", "behavior-desc", text=mod.DESCRIPTION))

            chips = el("div", "chips")
            for req in mod.REQUIRED:
                chips.appendChild(el("span", "chip", text=L.KIND_LABEL.get(req, req)))
            card.appendChild(chips)

            # card-color trigger chip (behavior index i -> color int i+1)
            cinfo = L.COLOR_INFO.get(i + 1)
            if cinfo:
                name, hexcol = cinfo
                trig = el("div", "trigger")
                dot = el("span", "trigger-dot")
                dot.style.background = hexcol
                trig.appendChild(dot)
                trig.appendChild(el("span", "trigger-label", text=f"{name} card"))
                card.appendChild(trig)

            on(card, "click", lambda e, m=mod: self._toggle(m))
            row.appendChild(card)
            self.behavior_cards.append({"mod": mod, "el": card, "index": i})

        self._refresh_behavior_availability()
        self._apply_page()

    def _refresh_behavior_availability(self):
        for bc in self.behavior_cards:
            avail = self._available(bc["mod"])
            bc["el"].classList.toggle("unavailable", not avail)
            bc["el"].classList.toggle("active", bc["mod"] is self.active_behavior)

    def _toggle(self, mod):
        if not self._available(mod):
            return
        if self.active_behavior is mod:
            self._deactivate()
        else:
            self._deactivate()
            self.active_behavior = mod
            if hasattr(mod, "on_start"):
                try:
                    mod.on_start(self._device_list())
                except Exception as e:
                    console.log("behavior on_start error:", repr(e))
            self._set_status(f"Behavior active: {mod.NAME}")
        self._refresh_behavior_availability()

    def _deactivate(self):
        if self.active_behavior and hasattr(self.active_behavior, "on_stop"):
            try:
                self.active_behavior.on_stop(self._device_list())
            except Exception as e:
                console.log("behavior on_stop error:", repr(e))
        self.active_behavior = None
        self._refresh_behavior_availability()

    def _activate_by_card_color(self, color_int):
        idx = color_int - 1
        if idx < 0 or idx >= len(self.behaviors):
            return
        mod = self.behaviors[idx]
        if not self._available(mod):
            return
        # jump to the page holding it
        self.page = idx // BEHAVIORS_PER_PAGE
        self._apply_page()
        self._toggle(mod)

    def _behavior_tick(self, *_):
        if not self.active_behavior:
            return
        try:
            self.active_behavior.tick(self._device_list())
        except Exception as e:
            console.log("behavior tick error:", repr(e))

    def _device_list(self):
        return [e["dev"] for e in self.devices.values()]

    # ── paging ──
    def _n_pages(self):
        return max(1, (len(self.behaviors) + BEHAVIORS_PER_PAGE - 1) // BEHAVIORS_PER_PAGE)

    def _turn_page(self, delta):
        self.page = (self.page + delta) % self._n_pages()
        self._apply_page()

    def _apply_page(self):
        start = self.page * BEHAVIORS_PER_PAGE
        end = start + BEHAVIORS_PER_PAGE
        for bc in self.behavior_cards:
            visible = start <= bc["index"] < end
            bc["el"].style.display = "flex" if visible else "none"
        byid("beh-page").textContent = f"{self.page + 1} / {self._n_pages()}"


_app = App()
_app.start()
