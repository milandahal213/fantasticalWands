import time
from lelib import singleMotor, controller

MOTOR_SERIAL      = 0   # replace with your single motor card serial
CONTROLLER_SERIAL = 0   # replace with your controller card serial

sm   = singleMotor()
ctrl = controller()

print("Connecting to Single Motor...")
sm.connect(MOTOR_SERIAL)
print("Connected to Single Motor.")

print("Connecting to Controller...")
ctrl.connect(CONTROLLER_SERIAL)
print("Connected to Controller.")

sm.device_notification_request(100)
ctrl.device_notification_request(100)

print("\n{'position':>10}  {'left':>6}  {'right':>6}")
print("-" * 32)

start = time.time()
while time.time() - start < 10:
    position = sm.motor.position
    left     = ctrl.sensor.leftPercent
    right    = ctrl.sensor.rightPercent
    print(f"{position:>10}  {left:>6}  {right:>6}")
    time.sleep(0.1)

sm.disconnect()
ctrl.disconnect()
print("\nDisconnected.")
