# main.py — the tapped card's COLOUR selects the wand's behaviour.
#
# Tap a LEGO connection card; its colour picks the mode. Tap a different
# connection card at any time to switch modes live (no button needed).
#
#   PURPLE / anything -> advertise_mode: "wand control" — broadcast an fd02
#       else             type-0x04 beacon whose speed tracks the accelerometer
#                        (wand tilt drives the motor). No GATT connection.
#   ORANGE           -> dance_mode:     broadcast RANDOM speeds to the double
#                       motor (a "dance") while showing the grouped colour
#                       sensor (matrix middle) and controller sticks (side
#                       columns) on the 5x5 grid. Also no GATT connection.
#   GREEN / BLUE     -> program_mode:   tap-programming. Every tap scans for
#                       devices that match that colour AND the tapped serial,
#                       and connects (GATT) to them.
#
# All three read the same tapped card's colour + serial + NFC-UID (the UID
# gives the beacon hash the motor validates).

from wand import Wand
from bledevice import BLEDevice
from legocast import advertise_mode, dance_mode, card_hash
from runloop import run_program_loop
from program_cards import read_card_universal_full, is_pairing_card
from newhub import SINGLE_MOTOR, DOUBLE_MOTOR
from cardpair import _scan_and_connect, _get_or_make_ui
import time

# ── which colours pick which mode ──────────────────────────────────────
# Colours are the app-aligned IDs returned by read_card_universal_full().
# Measured on hardware: purple=2, green=6, orange=9.
# BLUE=3 is NOT measured — it's inferred from remap_color()'s passthrough
# rule (raw firmware blue=3 has no entry in the remap table, so it passes
# through unchanged). That same identity assumption was WRONG for orange
# (raw 8 -> app 9, not 8), so treat 3 as a placeholder: tap the blue card,
# read the "tap: color=" print, and fix this if it differs.
DANCE_COLOR    = 9            # orange      -> dance
PROGRAM_COLORS = (6, 3)       # green, blue -> tap programming   (blue: CONFIRM!)
# every other colour (incl. purple=2) -> accelerometer advertise ("wand control")

w   = Wand()
ble = BLEDevice()
time.sleep(1)


# ── card reading ───────────────────────────────────────────────────────
def read_card(timeout_ms=200):
    """Read a connection card; return a full dict or None.
        {'uid', 'raw', 'app', 'serial', 'b2', 'b7'}
    raw = colour byte for the beacon; app = remapped colour for dispatch/UI;
    b2/b7 = beacon hash computed from the NFC UID."""
    r = read_card_universal_full(w, timeout_ms=timeout_ms)
    if r is None:
        return None
    uid, raw_color, app_color, serial = r
    b2, b7 = card_hash(uid)
    return {'uid': bytes(uid), 'raw': raw_color, 'app': app_color,
            'serial': serial, 'b2': b2, 'b7': b7}


def make_switch(current):
    """Return a switch() callable for dance/advertise modes: returns a NEW card
    dict when a DIFFERENT connection card is tapped, else None."""
    cur = (current['app'], current['serial'])

    def _switch():
        c = read_card(timeout_ms=120)
        if c is None:
            return None
        if not is_pairing_card(c['serial']):
            return None                        # a program card, not a mode card
        if (c['app'], c['serial']) == cur:
            return None                        # same card -> stay in this mode
        w.play_card_tap_jingle()
        return c
    return _switch


def prog_mode_switch(uid, raw_color, color, serial, current):
    """mode_switch for run_program_loop: leave program mode when a DIFFERENT
    connection card is tapped. Program action cards (high serial) keep us here;
    re-tapping the SAME connection card lets run_program_loop re-pair."""
    if (color, serial) == (current['app'], current['serial']):
        return None
    if not is_pairing_card(serial):
        return None
    w.play_card_tap_jingle()
    b2, b7 = card_hash(uid)
    return {'uid': bytes(uid), 'raw': raw_color, 'app': color,
            'serial': serial, 'b2': b2, 'b7': b7}


# ── program-mode plumbing (from the original main.py) ──────────────────
def on_data(slot_name, parsed):
    """Auto-arm motors on first telemetry (program mode)."""
    for s, hub, info in getattr(w, 'connections', []):
        if s != slot_name:
            continue
        if hub.data.get('_armed'):
            return
        pid = info['product_id']
        if pid == SINGLE_MOTOR:
            hub.motor_speed(1, 0); hub.motor_run(1, 0); hub.data['_armed'] = True
        elif pid == DOUBLE_MOTOR:
            hub.motor_speed(3, 0); hub.motor_run(3, 0); hub.data['_armed'] = True
        return


def disconnect_all():
    """Stop motors and drop every GATT connection, freeing the radio for the
    broadcast/scan used by dance and advertise modes."""
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


def program_mode(card):
    """Tap-programming for the tapped colour: pre-connect to that colour's
    devices, then run the program loop until a different connection card is
    tapped (returned for the dispatcher)."""
    ui = _get_or_make_ui(w)
    w.connections = getattr(w, 'connections', [])
    w.bound_card  = (card['app'], card['serial'])
    w.program     = []
    try: ui.set_card_color(card['app'])
    except: pass
    print("PROGRAM (colour {}) — connecting to its devices...".format(card['app']))
    new = _scan_and_connect(w, ble, card['app'], card['serial'],
                            existing=w.connections, scan_ms=1500, on_data=on_data)
    w.connections.extend(new)
    nxt = run_program_loop(
        w, ble, scan_ms=700, on_data=on_data,
        mode_switch=lambda u, r, c, s: prog_mode_switch(u, r, c, s, card))
    disconnect_all()                            # free the radio before broadcast
    return nxt


def wait_for_card():
    print("tap a connection card to pick a mode...")
    while True:
        w.pixels_card_prompt()
        c = read_card(timeout_ms=200)
        if c is not None:
            w.play_card_tap_jingle()
            return c


# ── dispatch loop ──────────────────────────────────────────────────────
card = wait_for_card()
try:
    while True:
        color = card['app']
        if color == DANCE_COLOR:
            nxt = dance_mode(w, ble, card, make_switch(card))
        elif color in PROGRAM_COLORS:
            nxt = program_mode(card)
        else:
            nxt = advertise_mode(w, ble, card, make_switch(card))
        card = nxt if nxt else wait_for_card()

except KeyboardInterrupt:
    try: ble.advertise_stop()
    except: pass
    try: ble.sensor_stop()
    except: pass
    disconnect_all()
    w.pixels_clear()
    print("stopped.")
