# ULTIMATE TEST — 4 devices simultaneously:
#   Controller  (input)  → drives Double Motor (tank drive, left motor inverted)
#   Color Sensor (input) → drives Single Motor (by brightness)
from bledevice import BLEDevice
from newhub import Hub
import time

# --- tuning ---
MAX_ANGLE      = 100   # controller angle for full motor speed
MAX_BRIGHTNESS = 100   # reflection value for full single-motor speed
MIN_SPEED      = 5     # deadband
UPDATE_MS      = 100
# --------------

MOTOR_LEFT  = 1
MOTOR_RIGHT = 2
MOTOR_BOTH  = 3
PORT_SINGLE = 1

def scale(value, max_val, invert=False):
    if value is None: return 0
    s = int(value * 100 / max_val)
    if invert: s = -s
    if s >  100: s =  100
    if s < -100: s = -100
    if abs(s) < MIN_SPEED: s = 0
    return s

# ─── BLE & hubs ─────────────────────────────────────────
ble = BLEDevice()
time.sleep(1)

def make_hub(slot_name):
    h = Hub(ble_device=ble, slot=slot_name)
    h.data = {}
    def cb(raw):
        try:
            r = h.parse([b for b in raw])
            if isinstance(r, dict):
                h.data.update(r)
        except Exception as e:
            print("{} parse err: {}".format(slot_name, e))
    h.set_callback(cb)
    return h

ctrl   = make_hub('ctrl')
dmotor = make_hub('dmotor')
color  = make_hub('color')
smotor = make_hub('smotor')

# ─── Connect all four, one at a time ────────────────────
print("Connecting Controller...")
ctrl.connect(Name='Controller');   ctrl.feed(200)

print("Connecting Double Motor...")
dmotor.connect(Name='Double Motor'); dmotor.feed(200)

print("Connecting Color Sensor...")
color.connect(Name='Color Sensor');  color.feed(200)

print("Connecting Single Motor...")
smotor.connect(Name='Single Motor'); smotor.feed(200)

print("\n*** All 4 devices connected! ***\n")
time.sleep(1)

# ─── Arm motors ─────────────────────────────────────────
dmotor.motor_speed(MOTOR_BOTH, 0)
dmotor.motor_run(MOTOR_BOTH, 0)
smotor.motor_speed(PORT_SINGLE, 0)
smotor.motor_run(PORT_SINGLE, 0)
print("Motors armed. Drive with controller; shine light on color sensor.")
print("Ctrl+C to stop.\n")

# ─── Control loop ───────────────────────────────────────
last_l = last_r = last_s = 0
try:
    while True:
        la = ctrl.data.get('leftAngle')
        ra = ctrl.data.get('rightAngle')
        br = color.data.get('reflection')

        lspeed = scale(la, MAX_ANGLE, invert=True)   # tank: invert left
        rspeed = scale(ra, MAX_ANGLE)
        sspeed = scale(br, MAX_BRIGHTNESS)

        if abs(lspeed - last_l) >= 2:
            dmotor.motor_speed(MOTOR_LEFT, lspeed);  last_l = lspeed
        if abs(rspeed - last_r) >= 2:
            dmotor.motor_speed(MOTOR_RIGHT, rspeed); last_r = rspeed
        if abs(sspeed - last_s) >= 2:
            smotor.motor_speed(PORT_SINGLE, sspeed); last_s = sspeed

        print("ctrl L={:4} R={:4}  bright={:4}  →  dmot L={:4} R={:4}  smot={:4}".format(
            la if la is not None else 0,
            ra if ra is not None else 0,
            br if br is not None else 0,
            lspeed, rspeed, sspeed))
        time.sleep_ms(UPDATE_MS)

except KeyboardInterrupt:
    print("\nStopping...")
    dmotor.motor_stop(MOTOR_BOTH)
    smotor.motor_stop(PORT_SINGLE)
    time.sleep(0.3)
    for slot in ('ctrl', 'dmotor', 'color', 'smotor'):
        ble.disconnect(slot)
    print("Done.")