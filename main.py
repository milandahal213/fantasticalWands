# main.py — LEGO single motor + light sensor → MIDI over WiFi/UDP to a Raspberry Pi
#
# What it does:
#   1. Connects (over BLE) to a LEGO Single Motor and a Color/Light sensor
#      using the same method as the Examples (BLEDevice + Hub).
#   2. Reads telemetry every loop:
#        - Motor position (degrees)  → the MIDI NOTE (pitch)
#        - Light "reflection" (0..100) → the VOLUME (MIDI CC 7, continuous)
#   3. Sends raw MIDI messages over UDP to the Pi, same wire format as before:
#        note on  = [0x90 | ch, note, velocity]
#        note off = [0x80 | ch, note, 0]
#        volume   = [0xB0 | ch, 7, value]        (Channel Volume)
#        program  = [0xC0 | ch, instrument]      (patch select, at startup)
#
# So: turn the motor to choose the pitch, and shine more/less light on the
# sensor to swell/fade the volume — even while a note is held.
#
# Tune everything in the CONFIG block below.

from newhub import Hub, COLOR_SENSOR, SINGLE_MOTOR
from bledevice import BLEDevice
import network
import socket
import time

# ─── CONFIG ────────────────────────────────────────────────────────────────
WIFI_SSID = "LocalNetwork"
WIFI_PASS = "musichackathon"

PI_IP   = "10.42.0.1"   # Raspberry Pi address (Pi hotspot gateway)
PI_PORT = 5010

CHANNEL  = 0            # MIDI channel used for the instrument
VELOCITY = 100          # 1..127 note-on attack (overall loudness is set by light)

# General MIDI instrument (program number, 0-based wire value).
# 57 = Trombone (GM program 58).  Sent as a Program Change at startup.
INSTRUMENT = 57

# Motor → note: linear map from |position| to a MIDI note, rounded to nearest.
#   |pos| = MOTOR_POS_MIN → MOTOR_NOTE_MIN,  |pos| = MOTOR_POS_MAX → MOTOR_NOTE_MAX.
#   Clamped to the MOTOR_NOTE_MIN..MOTOR_NOTE_MAX range.
MOTOR_POS_MIN  = 0
MOTOR_POS_MAX  = 800
MOTOR_NOTE_MIN = 65
MOTOR_NOTE_MAX = 85

# Light → volume: reflection 0..100 maps to MIDI CC 7 volume 0..127.
VOLUME_CC = 7           # 7 = Channel Volume

UPDATE_MS = 60          # sensor/telemetry update period
# ───────────────────────────────────────────────────────────────────────────


# ─── WiFi ──────────────────────────────────────────────────────────────────
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASS)
print("Connecting to WiFi...")
while not wlan.isconnected():
    time.sleep(0.1)
print("WiFi connected! IP:", wlan.ifconfig()[0])

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _send(msg):
    # ESP32 WiFi send buffers can briefly fill up (OSError ENOMEM / EAGAIN).
    # Retry a few times with a tiny pause instead of crashing.
    for _ in range(5):
        try:
            sock.sendto(msg, (PI_IP, PI_PORT))
            return
        except OSError:
            time.sleep_ms(3)
    # gave up on this message; drop it rather than kill the loop

def note_on(channel, note, velocity):
    _send(bytes([0x90 | channel, note & 0x7F, velocity & 0x7F]))

def note_off(channel, note):
    _send(bytes([0x80 | channel, note & 0x7F, 0]))

def control_change(channel, controller, value):
    _send(bytes([0xB0 | channel, controller & 0x7F, value & 0x7F]))

def program_change(channel, program):
    _send(bytes([0xC0 | channel, program & 0x7F]))


# ─── LEGO connection (same method as the Examples) ─────────────────────────
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

motor = make_hub('motor')
print("Connecting Single Motor...")
motor.connect(product_id=SINGLE_MOTOR)
motor.feed(UPDATE_MS)

light = make_hub('light')
print("Connecting Light sensor...")
light.connect(product_id=COLOR_SENSOR)
light.feed(UPDATE_MS)

print("\n*** LEGO connected — turn the motor, shine the light! ***\n")

# Select the instrument (trombone) on our channel.
program_change(CHANNEL, INSTRUMENT)
time.sleep(0.5)


def motor_position(hub):
    """The motor's key includes its port number (e.g. 'absolutePos0').
    Grab whichever position field the motor is reporting."""
    d = hub.data
    for k in d:
        if k.startswith('absolutePos'):
            return d[k]
    for k in d:
        if k.startswith('position'):
            return d[k]
    return None


# ─── Main loop ─────────────────────────────────────────────────────────────
last_note = None
last_volume = None

try:
    while True:
        # --- Light reflection → volume (CC 7), continuous ---
        reflection = light.data.get('reflection')
        if reflection is not None:
            volume = int(reflection * 127 / 100)
            volume = max(0, min(127, volume))
            if volume != last_volume:
                control_change(CHANNEL, VOLUME_CC, volume)
                last_volume = volume

        # --- Motor position → note (pitch) ---
        pos = motor_position(motor)
        if pos is None:
            target = None
        else:
            pos = abs(pos)
            span = MOTOR_POS_MAX - MOTOR_POS_MIN
            note = MOTOR_NOTE_MIN + (pos - MOTOR_POS_MIN) * (MOTOR_NOTE_MAX - MOTOR_NOTE_MIN) / span
            note = int(round(note))
            target = max(MOTOR_NOTE_MIN, min(MOTOR_NOTE_MAX, note))

        if target != last_note:
            if last_note is not None:
                note_off(CHANNEL, last_note)
            if target is not None:
                note_on(CHANNEL, target, VELOCITY)
                print("pos={:5}  note={}  vol={}".format(pos, target, last_volume))
            last_note = target

        time.sleep_ms(UPDATE_MS)

except KeyboardInterrupt:
    print("\nStopping — sending note off...")
    if last_note is not None:
        note_off(CHANNEL, last_note)
    time.sleep(0.2)
    try: motor.disconnect()
    except: pass
    try: light.disconnect()
    except: pass
    print("Done.")
