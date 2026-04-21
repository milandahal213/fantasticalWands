# Tap a Connection Card on the wand to pair with a LEGO Controller.
#
# LED + sound flow:
#   1) Waiting for tap     → faint white spinner on the outer ring
#   2) Card detected       → only the center pixel is lit (still white/faint)
#                            (this stays until the BLE connection succeeds)
#   3) BLE connected       → happy jingle plays
#                            grid shows a faint version of the card's color
from wand import Wand
from bledevice import BLEDevice
from newhub import Hub, SINGLE_MOTOR
import time

w   = Wand()
ble = BLEDevice()
time.sleep(1)

print("Tap a card on the wand...")
color, name, serial = w.read_card_named()
print("Got {} card, serial {:04d} — connecting...".format(name, serial))
# Center pixel is already lit by read_card() — leave it until BLE is up.

h = Hub(ble_device=ble, slot='x')
h.data = {}
def on_data(raw):
    r = h.parse([b for b in raw])
    if isinstance(r, dict):
        h.data.update(r)
h.set_callback(on_data)

h.connect(product_id=SINGLE_MOTOR, card_color=color, card_serial=serial)
h.feed(200)

# BLE is alive — celebrate
w.play_connect_jingle()
w.pixels_card_faint(color)
print("Connected. Move the joysticks. Ctrl+C to stop.\n")

try:
    while True:
        print("left={:5}  right={:5}".format(
            h.data.get('leftAngle','?'), h.data.get('rightAngle','?')))
        time.sleep(0.2)
except KeyboardInterrupt:
    w.pixels_clear()
    ble.disconnect('x')
    print("Done.")