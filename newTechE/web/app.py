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


# ---- connection state -> enable/disable buttons ----
def _set_connected(is_conn):
    status = document.getElementById("status")
    status.textContent = "connected" if is_conn else "not connected"
    status.className = "status on" if is_conn else "status off"
    document.getElementById("btn-connect").disabled = is_conn
    document.getElementById("btn-disconnect").disabled = not is_conn
    for bid in ("btn-flash", "run-run", "run-stop"):
        document.getElementById(bid).disabled = not is_conn


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


@when("click", "#btn-clear")
def _clear(evt):
    mp.clear()


# ---- run / stop the firmware, to watch its console output live ----
@when("click", "#run-run")
async def _run(evt):
    mp.clear()
    await mp.runProject("import broadcast_main; broadcast_main.main()")


@when("click", "#run-stop")
async def _run_stop(evt):
    await mp.interrupt()
    mp.log("[stopped]")


_set_connected(False)
