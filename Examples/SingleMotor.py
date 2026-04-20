from newhub import Hub, SINGLE_MOTOR
import time

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

print("Connecting to Single Motor...")
h.connect(product_id=SINGLE_MOTOR)
print("Connected!")
h.feed(updateTime=200)

while True:
    print("position:", h.data.get('position1', '?'))
    time.sleep(0.2)