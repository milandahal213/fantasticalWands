# Ultimate test: Controller angles drive Double Motor speeds
# Left angle  → left motor speed
# Right angle → right motor speed
from bledevice import BLEDevice
from newhub import Hub
import time

# --- tuning ---
MAX_ANGLE = 100    # raw angle value that maps to 100% speed (calibrate from output)
MIN_SPEED = 5      # deadband
UPDATE_MS = 100
# --------------

MOTOR_LEFT  = 1
MOTOR_RIGHT = 2
MOTOR_BOTH  = 3

def angle_to_speed(a):
    if a is None: return 0
    s = int(a * 100 / MAX_ANGLE)
    if s >  100: s =  100
    if s < -100: s = -100
    if abs(s) < MIN_SPEED: s = 0
    return s

ble = BLEDevice()
time.sleep(1)

# ─── Controller ──────────────────────────────────────────
ctrl = Hub(ble_device=ble, slot='ctrl')
ctrl.data = {}
def on_ctrl(raw):
    try:
        r = ctrl.parse([b for b in raw])
        if isinstance(r, dict):
            ctrl.data.update(r)
    except Exception as e:
        print("ctrl err:", e)
ctrl.set_callback(on_ctrl)

print("Connecting to Controller...")
ctrl.connect(Name='Controller')
ctrl.feed(updateTime=200)
print("Controller ready.\n")

time.sleep(0.5)

# ─── Motor ───────────────────────────────────────────────
motor = Hub(ble_device=ble, slot='motor')
motor.data = {}
def on_motor(raw):
    try:
        r = motor.parse([b for b in raw])
        if isinstance(r, dict):
            motor.data.update(r)
    except Exception as e:
        print("motor err:", e)
motor.set_callback(on_motor)

print("Connecting to Double Motor...")
motor.connect(Name='Double Motor')
motor.feed(updateTime=200)
print("Motor ready.\n")

time.sleep(1)

# Arm both motors at speed 0
motor.motor_speed(MOTOR_BOTH, 0)
motor.motor_run(MOTOR_BOTH, 0)
print("Both motors armed. Turn the controller dials. Ctrl+C to stop.\n")

last_l = 0
last_r = 0
try:
    while True:
        la = ctrl.data.get('leftAngle')
        ra = ctrl.data.get('rightAngle')
        lspeed = angle_to_speed(la)
        rspeed = angle_to_speed(ra)

        if abs(lspeed - last_l) >= 2:
            motor.motor_speed(MOTOR_LEFT, lspeed)
            last_l = lspeed
        if abs(rspeed - last_r) >= 2:
            motor.motor_speed(MOTOR_RIGHT, rspeed)
            last_r = rspeed

        print("L_angle={:5}→{:4}   R_angle={:5}→{:4}".format(
            la if la is not None else '?', lspeed,
            ra if ra is not None else '?', rspeed))
        time.sleep_ms(UPDATE_MS)

except KeyboardInterrupt:
    print("\nStopping...")
    motor.motor_stop(MOTOR_BOTH)
    time.sleep(0.3)
    ble.disconnect('motor')
    ble.disconnect('ctrl')
    print("Done.")