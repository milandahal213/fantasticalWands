from newhub import Hub
import time

DEVICE_NAME = 'Double Motor'

h = Hub()
time.sleep(2)

def on_data(raw):
    # Print the raw bytes as a hex list so we can see the exact packet structure
    print([hex(b) for b in raw])

h.set_callback(on_data)

print("Connecting to '{}' …".format(DEVICE_NAME))
h.connect(Name=DEVICE_NAME)
print("Connected! Waiting for raw packets…")

h.feed(updateTime=200)   # slower feed so output is readable

while True:
    time.sleep(0.1)