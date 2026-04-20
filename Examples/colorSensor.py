from newhub import Hub
import time

DEVICE_NAME = 'Color Sensor'

h = Hub()
h.data = {}
time.sleep(2)

def on_data(raw):
    try:
        result = h.parse([b for b in raw])
        if isinstance(result, dict):
            h.data.update(result)
    except Exception as e:
        print("ERR:", e)

h.set_callback(on_data)

print("Connecting to '{}' ...".format(DEVICE_NAME))
h.connect(Name=DEVICE_NAME)
print("Connected!")

h.feed(updateTime=200)

while True:
    d = h.data
    print("color:{:4}  reflect:{:4}  R:{:4}  G:{:4}  B:{:4}  clear:{:5}  IR:{:5}".format(
        d.get('color',      '?'),
        d.get('reflection', '?'),
        d.get('rawRed',     '?'),
        d.get('rawGreen',   '?'),
        d.get('rawBlue',    '?'),
        d.get('clear',      '?'),
        d.get('infrared',   '?')))
    time.sleep(0.2)