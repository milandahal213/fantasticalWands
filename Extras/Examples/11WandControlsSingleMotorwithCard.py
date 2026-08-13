# Wand accelerometer controls a Single Motor.
# Tilt the wand forward/back: tilting one way spins the motor clockwise,
# the other way spins it counter-clockwise. Level = stopped.
#
# Tap any card first to pair, then tilt to drive.

from wand import Wand
from bledevice import BLEDevice
from newhub import Hub, SINGLE_MOTOR
import time

# --- tuning ---
TILT_FULL   = 0.7    # g of X-axis tilt that maps to 100% speed
MIN_SPEED   = 5      # deadband
UPDATE_MS   = 100
# --------------

MOTOR_PORT = 1

def tilt_to_speed(g):
    s = int(g * 100 / TILT_FULL)
    if s >  100: s =  100
    if s < -100: s = -100
    if abs(s) < MIN_SPEED: s = 0
    return s

w   = Wand()
ble = BLEDevice()
time.sleep(1)

# ─── Pair motor via card tap ──────────────────────────
print("Tap any card on the wand to pair with the Single Motor...")
color, name, serial = w.read_card_named()
print("Got {} card (serial {:04d}). Connecting...".format(name, serial))

h = Hub(ble_device=ble, slot='smotor')
h.data = {}
def on_data(raw):
    r = h.parse([b for b in raw])
    if isinstance(r, dict): h.data.update(r)
h.set_callback(on_data)

h.connect(product_id=SINGLE_MOTOR, card_color=color, card_serial=serial)
h.feed(200)

w.set_device_state('smotor', 'connected')
w.refresh_status()
w.play_connect_jingle()
print("Connected! Arming motor...")

# Arm motor so motor_speed() updates take effect immediately
h.motor_speed(MOTOR_PORT, 0)
h.motor_run(MOTOR_PORT, 0)

# ─── Init accelerometer ───────────────────────────────
accel = w.accel
print("Tilt the wand to drive the motor. Ctrl+C to stop.\n")

# ─── Control loop ─────────────────────────────────────
last_speed = 0
try:
    while True:
        x, y, z = accel.read()
        speed = tilt_to_speed(x)
        if abs(speed - last_speed) >= 2:
            h.motor_speed(MOTOR_PORT, speed)
            last_speed = speed
        print("x={:+.2f}g  y={:+.2f}g  z={:+.2f}g   →  speed={:+4d}".format(
            x, y, z, speed))
        time.sleep_ms(UPDATE_MS)

except KeyboardInterrupt:
    print("\nStopping...")
    h.motor_stop(MOTOR_PORT)
    time.sleep(0.3)
    ble.disconnect('smotor')
    w.pixels_clear()
    print("Done.")