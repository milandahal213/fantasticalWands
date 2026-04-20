from newhub import Hub
import time

DEVICE_NAME = 'Double Motor'

h = Hub()
h.data = {}   # store telemetry on hub object to avoid closure scoping issues
time.sleep(2)

def on_data(raw):
    try:
        result = h.parse([b for b in raw])
        if isinstance(result, dict):
            h.data.update(result)
    except Exception as e:
        print("on_data ERR:", e)

h.set_callback(on_data)

print("Connecting to '{}' ...".format(DEVICE_NAME))
h.connect(Name=DEVICE_NAME)
print("Connected!")

h.feed(updateTime=200)

while True:
    d = h.data
    print("pos1:{:6}  pos2:{:6}  yaw:{:6}  pitch:{:6}  roll:{:6}".format(
        d.get('position1', '?'),
        d.get('position2', '?'),
        d.get('yaw',       '?'),
        d.get('pitch',     '?'),
        d.get('roll',      '?')))
    time.sleep(0.1)