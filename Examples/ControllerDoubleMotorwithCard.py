# Controller drives Double Motor — tank drive (left motor inverted)
# Devices are found by product_id instead of name.
from bledevice import BLEDevice
from newhub import (Hub, PRODUCT_CONTROLLER, PRODUCT_DOUBLE_MOTOR)
import time

# --- tuning ---
MAX_ANGLE = 100
MIN_SPEED = 5
UPDATE_MS = 100
# --------------

MOTOR_LEFT  = 1
MOTOR_RIGHT = 2
MOTOR_BOTH  = 3

def angle_to_speed(a, invert=False):
    if a is None: return 0
    s = int(a * 100 / MAX_ANGLE)
    if invert: s = -s
    if s >  100: s =  100
    if s < -100: s = -100
    if abs(s) < MIN_SPEED: s = 0
    return s

ble = BLEDevice()
time.sleep(1)

def make_hub(slot_name):
    h = Hub(ble_device=ble, slot=slot_name)
    h.data = {}
    def cb(raw):
        r = h.parse([b for b in raw])
        if isinstance(r, dict):
            h.data.update(r)
    h.set_callback(cb)
    return h

ctrl  = make_hub('ctrl')
motor = make_hub('motor')

print("Connecting to Controller...")
ctrl.connect(product_id=PRODUCT_CONTROLLER); ctrl.feed(200)

print("Connecting to Double Motor...")
motor.connect(product_id=PRODUCT_DOUBLE_MOTOR); motor.feed(200)

time.sleep(1)
motor.motor_speed(MOTOR_BOTH, 0)
motor.motor_run(MOTOR_BOTH, 0)
print("\nMotors armed. Drive with the controller. Ctrl+C to stop.\n")

last_l = last_r = 0
try:
    while True:
        la = ctrl.data.get('leftAngle')
        ra = ctrl.data.get('rightAngle')

        lspeed = angle_to_speed(la, invert=True)   # tank: invert left
        rspeed = angle_to_speed(ra)

        if abs(lspeed - last_l) >= 2:
            motor.motor_speed(MOTOR_LEFT, lspeed);  last_l = lspeed
        if abs(rspeed - last_r) >= 2:
            motor.motor_speed(MOTOR_RIGHT, rspeed); last_r = rspeed

        print("L_angle={:5}→{:4}   R_angle={:5}→{:4}".format(
            la if la is not None else 0, lspeed,
            ra if ra is not None else 0, rspeed))
        time.sleep_ms(UPDATE_MS)

except KeyboardInterrupt:
    print("\nStopping...")
    motor.motor_stop(MOTOR_BOTH)
    time.sleep(0.3)
    ble.disconnect('ctrl')
    ble.disconnect('motor')
    print("Done.")