# Tap a Connection Card on the wand to pair with a LEGO Controller.
# NeoPixels do the talking:
#   - rainbow breathing while waiting for a card
#   - flash + hold the card's color once tapped
#   - goes dim when the BLE connection is live
from wand import Wand
from bledevice import BLEDevice
from newhub import Hub, SINGLE_MOTOR
import time

w   = Wand()
ble = BLEDevice()
time.sleep(1)

print("Tap a card on the wand...")
color, name, serial = w.read_card_named()
print("Got {} card, serial {:04d}".format(name, serial))
w.beep(1500, 80)

h = Hub(ble_device=ble, slot='x')
h.data = {}
def on_data(raw):
    r = h.parse([b for b in raw])
    if isinstance(r, dict):
        h.data.update(r)
h.set_callback(on_data)

print("Connecting to Controller...")
h.connect(product_id=SINGLE_MOTOR, card_color=color, card_serial=serial)
h.feed(200)

# Dim the color now that we're connected
w.pixel_brightness = 0.05
w.pixels_fill_card(color)
w.beep(2000, 60)
print("Connected. Move the joysticks. Ctrl+C to stop.\n")

try:
    while True:
        print("Position={:5} ".format(
            h.data.get('absolutePos1','?')))
        time.sleep(0.2)
except KeyboardInterrupt:
    w.pixels_clear()
    ble.disconnect('x')
    print("Done.")