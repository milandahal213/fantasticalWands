"""
app.py - PyScript front-end. Wires the page buttons to the Web Serial driver
(micropico.js). The gnarly byte-level serial protocol lives in JS; the app
logic (what each button does) lives here in Python.
"""

from js import document, MicroPico
from pyodide.ffi import create_proxy
from pyscript import when

repl = document.getElementById("repl")
repl.textContent = ""
mp = MicroPico.new(repl)

# Bridge behavior metadata (title + human-readable required devices).
BRIDGE_META = {
    "tank":        ("Tank Drive",     "Controller + Double Motor"),
    "arcade":      ("Arcade Drive",   "Controller + Double Motor"),
    "color_speed": ("Color Speed",    "Color Sensor + Double Motor"),
    "color_steer": ("Color + Steer",  "Color Sensor + Controller + Double Motor"),
    "knob":        ("Knob Throttle",  "Single Motor + Double Motor"),
    "tilt":        ("Tilt Drive",     "Double Motor + Single Motor"),
}
_bridge = {"beh": None}


# ---- connection state -> enable/disable buttons ----
def _set_connected(is_conn):
    status = document.getElementById("status")
    status.textContent = "connected" if is_conn else "not connected"
    status.className = "status on" if is_conn else "status off"
    document.getElementById("btn-connect").disabled = is_conn
    document.getElementById("btn-disconnect").disabled = not is_conn
    for bid in ("btn-flash", "p1-run", "p1-stop", "bridge-stop"):
        document.getElementById(bid).disabled = not is_conn
    # bridge Start needs both a connection and a selected behavior
    document.getElementById("bridge-run").disabled = not (is_conn and _bridge["beh"])
    hint = document.getElementById("bridge-hint")
    if hint:
        hint.textContent = ("Tap the device cards, then the Pico." if is_conn
                            else "Connect the Pico (top-right) to enable Start.")


mp.onConnectChange = create_proxy(_set_connected)


# ---- connection ----
@when("click", "#btn-connect")
async def _connect(evt):
    try:
        await mp.connect()
    except Exception as e:  # noqa: BLE001
        mp.log("[error] " + str(e))


@when("click", "#btn-disconnect")
async def _disconnect(evt):
    await mp.disconnect()


# ---- flashing ----
@when("click", "#btn-flash")
async def _flash(evt):
    prog = document.getElementById("flash-progress")

    def on_progress(done, total, name):
        prog.textContent = ("done" if done >= total else
                            "%d/%d  %s" % (done, total, name))

    mp.log("[flashing firmware...]")
    try:
        # firmware lives at the repo root, one level up from /web
        await mp.flashFromManifest("manifest.json", "../", create_proxy(on_progress))
        await mp.softReset()   # reload freshly-flashed modules
        mp.log("[flash complete - Pico rebooted]")
    except Exception as e:  # noqa: BLE001
        mp.log("[flash error] " + str(e))


# ---- Project 1: Tap & Connect ----
@when("click", "#p1-run")
async def _p1_run(evt):
    oled = document.getElementById("p1-oled").checked
    mp.clear()
    flag = "True" if oled else "False"
    await mp.runProject("import project1; project1.run(oled=%s)" % flag)


@when("click", "#p1-stop")
async def _p1_stop(evt):
    await mp.interrupt()
    mp.log("[stopped]")


@when("click", "#btn-clear")
def _clear(evt):
    mp.clear()


# ---- Bridge: pick a behavior card, then Start/Stop ----
@when("click", ".beh-card")
def _bridge_pick(evt):
    card = evt.currentTarget
    beh = card.dataset.beh
    _bridge["beh"] = beh
    title, needs = BRIDGE_META[beh]
    document.getElementById("setup-title").textContent = title
    document.getElementById("setup-needs").textContent = needs
    document.getElementById("bridge-setup").classList.remove("hidden")
    for c in document.querySelectorAll(".beh-card"):
        c.classList.toggle("selected", c.dataset.beh == beh)
    document.getElementById("bridge-run").disabled = not mp.connected


@when("click", "#bridge-run")
async def _bridge_start(evt):
    beh = _bridge["beh"]
    if not beh:
        return
    oled = document.getElementById("bridge-oled").checked
    mp.clear()
    flag = "True" if oled else "False"
    await mp.runProject('import bridge; bridge.run("%s", oled=%s)' % (beh, flag))


@when("click", "#bridge-stop")
async def _bridge_stop(evt):
    await mp.interrupt()
    mp.log("[stopped]")


_set_connected(False)
