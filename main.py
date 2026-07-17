# main.py — LEGO single motor + light sensor → MIDI over WiFi/UDP to a Raspberry Pi
#
# What it does:
#   1. Connects (over BLE) to a LEGO Single Motor and a Color/Light sensor
#      using the same method as the Examples (BLEDevice + Hub).
#   2. Reads telemetry every loop:
#        - Motor position (degrees)    → the MIDI NOTE (pitch)
#        - Light "reflection" (0..100) → the TRIGGER: a >=30% swing fires a note
#   3. Sends raw MIDI messages over UDP to the Pi, same wire format as before:
#        note on  = [0x90 | ch, note, velocity]
#        note off = [0x80 | ch, note, 0]
#        program  = [0xC0 | ch, instrument]      (patch select, at startup)
#
# So: aim the pitch with the motor, then "strike" the note by changing the
# light on the sensor (wave a hand, cover/uncover it).
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

# Light → trigger: fire a note when the reflection value changes by this much
# (relative to the value at the last trigger). 0.30 = a 30% swing.
TRIGGER_PCT   = 0.30
TRIGGER_FLOOR = 2       # ...but require at least this many points of change (noise guard)

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


def motor_note(hub):
    """Current motor position → MIDI note (pitch), or None if no data yet."""
    pos = motor_position(hub)
    if pos is None:
        return None, None
    pos = abs(pos)
    span = MOTOR_POS_MAX - MOTOR_POS_MIN
    note = MOTOR_NOTE_MIN + (pos - MOTOR_POS_MIN) * (MOTOR_NOTE_MAX - MOTOR_NOTE_MIN) / span
    note = int(round(note))
    return max(MOTOR_NOTE_MIN, min(MOTOR_NOTE_MAX, note)), pos


# ─── Main loop ─────────────────────────────────────────────────────────────
# Motor position picks the pitch; a >=30% swing in reflection fires the note.
last_note = None
ref_reflection = None   # reflection value at the last trigger (the baseline)

try:
    while True:
        reflection = light.data.get('reflection')
        if reflection is not None:
            if ref_reflection is None:
                ref_reflection = reflection            # establish baseline, no trigger
            else:
                delta = abs(reflection - ref_reflection)
                threshold = max(TRIGGER_FLOOR, TRIGGER_PCT * ref_reflection)
                if delta >= threshold:
                    note, pos = motor_note(motor)
                    if last_note is not None:
                        note_off(CHANNEL, last_note)   # release previous note
                    if note is not None:
                        note_on(CHANNEL, note, VELOCITY)
                        print("TRIGGER  refl {}->{}  pos={}  note={}".format(
                            ref_reflection, reflection, pos, note))
                        last_note = note
                    ref_reflection = reflection         # new baseline

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
