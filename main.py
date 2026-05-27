# Tangible programming system for LEGO via the wand.
#
# Flow:
#   1. Tap a pairing card. Wand finds and connects to LEGO devices.
#   2. Tap programming cards in order — each adds a "block" to the program.
#      The bottom 3 rows of the LED grid show your deck, color-coded by
#      category (motion=teal, sensing=pink, event=yellow, control=orange,
#      meta=white).
#   3. Tap the GO card (serial 9000) to run.
#   4. Tap the ERASE card (serial 9001) to clear the deck.
#   5. Mix in new pairing card taps any time to add more LEGO devices
#      (same pairing card only — different one is rejected).
#
# LED layout:
#   Row 0    — connected devices (solid pixel each)
#   Rows 1-3 — program deck (one pixel per block, category-colored)
#              or execution cursor (bright pixel = current step)
#   Row 4    — bound pairing card color

from wand import Wand
from bledevice import BLEDevice
from runloop import run_program_loop
from newhub import SINGLE_MOTOR, DOUBLE_MOTOR
import time

w   = Wand()
ble = BLEDevice()
time.sleep(1)


def on_data(slot_name, parsed):
    """Auto-arm motors on first telemetry."""
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


try:
    run_program_loop(w, ble, scan_ms=700, on_data=on_data)
except KeyboardInterrupt:
    for slot, hub, info in w.connections:
        pid = info['product_id']
        if pid in (SINGLE_MOTOR, DOUBLE_MOTOR):
            try: hub.motor_stop(3 if pid == DOUBLE_MOTOR else 1)
            except: pass
    time.sleep(0.3)
    for slot, _, _ in w.connections:
        try: ble.disconnect(slot)
        except: pass
    w.pixels_clear()