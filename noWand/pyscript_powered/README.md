# noWand — PyScript edition

A **100% browser-based** version of noWand for controlling LEGO Education hardware
(Single Motor, Double Motor, Color Sensor, Controller) over Bluetooth. No Python
install, no `pip`, nothing to download — just open the page. The UI is HTML/CSS,
the logic is Python running in your browser via [PyScript](https://pyscript.net),
and Bluetooth goes through the browser's **Web Bluetooth** API.

This is a self-contained sibling of the desktop (Tkinter) app — it can be hosted
as static files (e.g. GitHub Pages) and shared with a single link.

---

## Requirements

- **A Chromium browser** — Chrome or Edge. Web Bluetooth is **not** available in
  Firefox or Safari.
- **A secure context** — `https://` (e.g. GitHub Pages) **or** `http://localhost`.
  Opening the file directly with `file://` will not work.
- LEGO Education hardware with Bluetooth.

---

## Run it locally

From inside this `pyscript_powered/` folder:

```bash
python3 -m http.server 8000
```

Then open **http://localhost:8000** in Chrome or Edge. (`localhost` counts as a
secure context, so Web Bluetooth works.)

Click **“+ Add device”**, pick your LEGO device from the browser's dialog, and it
connects. Add more devices the same way.

---

## Host it on GitHub Pages

1. Commit this `pyscript_powered/` folder to your repo.
2. In the repo: **Settings → Pages**, set the source to your branch and folder.
3. Visit the published `https://…github.io/…/pyscript_powered/` URL in Chrome/Edge.

Because GitHub Pages serves over HTTPS, Web Bluetooth works out of the box.

---

## How it works

| Layer | File | Role |
|-------|------|------|
| UI | `index.html`, `style.css` | Layout and styling (replaces Tkinter) |
| App | `main.py` | Builds the DOM, manages connections, telemetry, behaviors |
| Bluetooth | `ble.py` | Thin wrapper over the Web Bluetooth API |
| Protocol | `lego_ble.py` | Re-implements the LEGO RPC wire protocol (commands + notifications) |
| Behaviors | `behaviors/` | One module per behavior (auto-discovered) |

The native `legoeducation` / `bleak` packages can't run in a browser sandbox, so
`lego_ble.py` re-creates the exact byte-level protocol they use (GATT service
`0xFD02`, write/notify characteristics, the command frames and notification
parsing). Its output is byte-for-byte identical to the official library.

### Differences from the desktop app

- **Connecting** uses the browser's built-in device chooser instead of a custom
  scan strip — that's how Web Bluetooth works (it won't let a page silently scan).
- **Card color & serial** are read from the device's notifications *after*
  connecting (shown on each card), rather than from the pre-connect advertisement.
- **Emoji and SVG icons render natively** in the browser — no `cairosvg`/`libcairo`
  and none of the macOS emoji-rendering crashes the desktop app had to work around.

---

## Behaviors

Click a behavior card to toggle it on/off. Only one runs at a time. You can also
**tap a colored card** on any connected device to switch behaviors hands-free:

| Card color | Behavior |
|------------|----------|
| Red | 1 — Tank Drive |
| Yellow | 2 — Arcade Drive |
| Blue | 3 — Light Theremin |
| Teal | 4 — Color Speed Map |
| Green | 5 — Alarm System |
| … | (color int *N* → behavior *N*) |

A behavior is greyed out until all its required devices are connected, and it
stops automatically if a required device disconnects.

### Add your own behavior

1. Create `behaviors/behavior6.py`:

   ```python
   from behaviors.util import find

   NAME = "My Behavior"
   DESCRIPTION = "One-line description"
   REQUIRED = ["controller", "double_motor"]   # device kinds needed

   def tick(devices):           # called ~16×/sec while active
       ctrl = find(devices, "controller")
       motor = find(devices, "double_motor")
       if ctrl and motor:
           motor.move_tank(ctrl.left or 0, ctrl.right or 0)

   def on_start(devices): ...   # optional
   def on_stop(devices):        # optional — clean up here
       m = find(devices, "double_motor")
       if m: m.stop()
   ```

   Device kinds: `"single_motor"`, `"double_motor"`, `"color_sensor"`, `"controller"`.

2. Register it in **two** places:
   - `behaviors/__init__.py` → add `"behavior6"` to `MODULE_NAMES`
   - `pyscript.toml` → add `"./behaviors/behavior6.py" = "./behaviors/behavior6.py"`
     under `[files]` (so the browser mounts the file)

Reload the page — it appears automatically, triggered by the Teal-card / 6th color.

### Device API available to behaviors

- Motors: `dev.run(speed)` (−100…100), `dev.stop()`, and `dev.move_tank(l, r)`
  (double motor only)
- All devices: `dev.beep(count=1)`
- Telemetry: `position`, `speed` (single); `pos_l/pos_r/speed_l/speed_r/yaw`
  (double); `left`, `right` (controller); `color`, `color_name`, `reflection`
  (color sensor); `card_color`, `card_serial` (any)

---

## Troubleshooting

**“Web Bluetooth not available”** — You're not in Chrome/Edge, or not on a secure
context. Use Chrome/Edge over `https://` or `http://localhost`.

**The “+ Add device” dialog is empty** — Make sure the device is powered on and not
already connected to another app or tab (LEGO Education app, the desktop noWand, or
another browser tab). Only one connection per device at a time.

**Nothing happens after picking a device** — Open the browser DevTools console
(F12). PyScript and protocol errors are logged there.

**Page is stuck on “Starting Python…”** — The pinned PyScript version may be
unreachable. Check the version in `index.html` and `pyscript.toml`'s loader against
the latest at [pyscript.net/releases](https://pyscript.net/releases/), or switch the
two URLs in `index.html` to use `…/releases/latest/…`.

**Sensor values show `…`** — Normal for the first 1–2 seconds after connecting,
while the first notification arrives. If it persists, reset the device.

---

## File structure

```
pyscript_powered/
  index.html           # page shell + PyScript loader
  style.css            # all styling
  pyscript.toml        # mounts the Python modules into the browser FS
  main.py              # app logic (entry point)
  ble.py               # Web Bluetooth bridge
  lego_ble.py          # LEGO RPC protocol (commands + notification parsing)
  behaviors/
    __init__.py        # registry (MODULE_NAMES)
    util.py            # find()/clamp() helpers
    behavior1.py … behavior5.py
  icons/
    single_motor.svg  double_motor.svg  color_sensor.svg  controller.svg
    emoji/             # one SVG per card color
```
