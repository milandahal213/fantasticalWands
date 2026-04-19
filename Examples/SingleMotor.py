from newhub import Hub
import time

DEVICE_NAME = 'Single Motor'

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

h.callback(on_data)

print("Connecting to '{}' ...".format(DEVICE_NAME))
h.connect(Name=DEVICE_NAME)
print("Connected!")

h.feed(updateTime=200)

while True:
    print("position:", h.data.get('position1', '?'))
    time.sleep(0.2)