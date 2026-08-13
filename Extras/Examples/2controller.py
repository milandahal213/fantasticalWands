from newhub import Hub, CONTROLLER
import time

h = Hub()
time.sleep(2)

telemetry = {}
def on_data(raw):
    result = h.parse([b for b in raw])
    if isinstance(result, dict):
        telemetry.update(result)
h.set_callback(on_data)


h.connect(product_id=CONTROLLER) #, card_color=CARD_GREEN, card_serial=26)
print("Connected! Move the joysticks.")
h.feed(updateTime=200)

while True:
    left  = telemetry.get('leftAngle',  '?')
    right = telemetry.get('rightAngle', '?')
    print("left: {:6}   right: {:6}".format(left, right))
    time.sleep(0.1)