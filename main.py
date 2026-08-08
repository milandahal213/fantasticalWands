# Tangible programming system for LEGO via the wand — with an accelerometer
# "advertise" mode.
#
# Two modes, toggled by holding the button > 1.5 s:
#
#   ADVERTISE (default) — the wand broadcasts an fd02 LEGO beacon whose b5/b6
#       track the accelerometer, so a motor tapped with the bound card drives
#       itself from wand tilt. No connection needed. (lib/legocast.py)
#
#   CONNECT — the original card-programming system: tap pairing/program cards,
#       GO to run. Unchanged. (lib/runloop.py)
#
# On boot you tap the pairing card once to bind it (colour, serial, and the
# hash computed from the card's NFC UID). Both modes then use that card.
#
# LED layout (connect mode):
#   Row 0    — connected devices          Rows 1-3 — program deck / cursor
#   Row 4    — bound pairing card color

from wand import Wand
from bledevice import BLEDevice
from runloop import run_program_loop
from newhub import SINGLE_MOTOR, DOUBLE_MOTOR
from legocast import ModeButton, bind_card, advertise_mode
import time

w   = Wand()
ble = BLEDevice()
time.sleep(1)


def on_data(slot_name, parsed):
    """Auto-arm motors on first telemetry (connect mode)."""
    for s, hub, info in w.connections:
        if s != slot_name: continue
        if hub.data.get('_armed'): return
        pid = info['product_id']
        if pid == SINGLE_MOTOR:
            hub.motor_speed(1, 0); hub.motor_run(1, 0)
            hub.data['_armed'] = True
        elif pid == DOUBLE_MOTOR:
            hub.motor_speed(3, 0); hub.motor_run(3, 0)
            hub.data['_armed'] = True
        return


def disconnect_all():
    """Stop motors and drop every GATT connection. Called when leaving connect
    mode so the radio is free to broadcast in advertise mode."""
    conns = getattr(w, 'connections', [])
    for slot, hub, info in conns:
        pid = info.get('product_id')
        if pid in (SINGLE_MOTOR, DOUBLE_MOTOR):
            try: hub.motor_stop(3 if pid == DOUBLE_MOTOR else 1)
            except: pass
    time.sleep(0.2)
    for slot, _, _ in conns:
        try: ble.disconnect(slot)
        except: pass
    time.sleep(0.3)
    w.connections = []
    ui = getattr(w, 'ui', None)
    if ui is not None:
        try: ui.clear_all()
        except: pass


# ── Bind a card at boot, then toggle advertise ⇄ connect on long-press ──
card = bind_card(w)                       # (beacon_color, serial, b2, b7, app_color)
w.bound_card = (card[4], card[1])          # (app_color, serial) — pre-bind connect mode
modebtn = ModeButton(w)

try:
    mode = 'advertise'
    while True:
        if mode == 'advertise':
            advertise_mode(w, ble, card, modebtn)          # returns on long-press
            w.beep(1200, 60)
            mode = 'connect'
        else:
            run_program_loop(w, ble, scan_ms=700, on_data=on_data,
                             should_exit=modebtn.check)     # returns on long-press
            disconnect_all()                                # drop motors before broadcasting
            w.beep(1800, 60)
            mode = 'advertise'

except KeyboardInterrupt:
    ble.advertise_stop()
    for slot, hub, info in getattr(w, 'connections', []):
        pid = info['product_id']
        if pid in (SINGLE_MOTOR, DOUBLE_MOTOR):
            try: hub.motor_stop(3 if pid == DOUBLE_MOTOR else 1)
            except: pass
    time.sleep(0.3)
    for slot, _, _ in getattr(w, 'connections', []):
        try: ble.disconnect(slot)
        except: pass
    w.pixels_clear()
