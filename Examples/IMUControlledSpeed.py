# IMU → Dual Motor control
# Pitch (tilt forward/back) drives the LEFT motor
# Roll  (tilt left/right)   drives the RIGHT motor
from bledevice import BLEDevice
from newhub import Hub
import time

# --- tuning ---
MAX_TILT   = 500   # raw axis value mapped to full speed
MIN_SPEED  = 5     # deadband
UPDATE_MS  = 100
# --------------

MOTOR_LEFT  = 1
MOTOR_RIGHT = 2
MOTOR_BOTH  = 3

def tilt_to_speed(axis):
    if axis is None: return 0
    s = int(axis * 100 / MAX_TILT)
    if s >  100: s =  100
    if s < -100: s = -100
    if abs(s) < MIN_SPEED: s = 0
    return s

ble = BLEDevice()
time.sleep(1)

h = Hub(ble_device=ble, slot='motor')
h.data = {}

def on_data(raw):
    try:
        result = h.parse([b for b in raw])
        if isinstance(result, dict):
            h.data.update(result)
    except Exception as e:
        print("parse err:", e)

h.set_callback(on_data)

print("Connecting to Double Motor...")
h.connect(Name='Double Motor')
h.feed(updateTime=200)
print("Connected.")

time.sleep(1)

# Start both motors running — motor_speed updates then control speed+direction
h.motor_speed(MOTOR_BOTH, 0)
h.motor_run(MOTOR_BOTH, 0)
print("Motors armed. Tilt to control. Ctrl+C to stop.\n")

last_left  = 0
last_right = 0
try:
    while True:
        left  = tilt_to_speed(h.data.get('pitch'))
        right = tilt_to_speed(h.data.get('roll'))

        if abs(left - last_left) >= 2:
            h.motor_speed(MOTOR_LEFT, left)
            last_left = left
        if abs(right - last_right) >= 2:
            h.motor_speed(MOTOR_RIGHT, right)
            last_right = right

        print("pitch={:5d} → L={:4d}   roll={:5d} → R={:4d}".format(
            h.data.get('pitch') or 0, left,
            h.data.get('roll')  or 0, right))
        time.sleep_ms(UPDATE_MS)

except KeyboardInterrupt:
    print("\nStopping...")
    h.motor_stop(MOTOR_BOTH)
    time.sleep(0.3)
    ble.disconnect('motor')
    print("Done.")