# main.py — LEGO light sensor + single motor → MIDI over WiFi/UDP to a Raspberry Pi
#
# What it does:
#   1. Connects (over BLE) to a LEGO Color/Light sensor and a Single Motor
#      using the same method as the Examples (BLEDevice + Hub).
#   2. Reads telemetry every loop:
#        - Light sensor "reflection" (0..100)  → a MIDI note   (voice 1, channel 0)
#        - Single motor position (degrees)      → a MIDI note   (voice 2, channel 1)
#   3. Sends raw 3-byte MIDI messages over UDP to the Pi, exactly like the
#      hackathon controller did:
#        note on  = [0x90 | channel, note, velocity]
#        note off = [0x80 | channel, note, 0]
#
# On the Pi, whatever was already listening on PI_PORT for MIDI bytes will play
# these. (The Pi is the UDP receiver — same as 10.42.0.1:5010 before.)
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

# Turn each voice on/off independently.
USE_LIGHT = True        # light reflection → notes on LIGHT_CHANNEL
USE_MOTOR = True        # motor position   → notes on MOTOR_CHANNEL

LIGHT_CHANNEL = 0
MOTOR_CHANNEL = 1

VELOCITY = 100          # 1..127 loudness of every note

# General MIDI instrument (program number, 0-based wire value).
# 57 = Trombone (GM program 58).  Sent as a Program Change at startup.
INSTRUMENT = 57

# Musical scale used for both voices (C-major pentatonic, 2 octaves = 10 notes).
ROOT      = 60          # MIDI note 60 = middle C
OCTAVES   = 2
PENTATONIC = [0, 2, 4, 7, 9]   # semitone offsets within an octave

# Light voice: reflection below this = silence (cover the sensor to stop).
LIGHT_GATE = 3          # reflection 0..100

# Motor voice: linear map from |position| to a MIDI note, rounded to nearest.
#   |pos| = MOTOR_POS_MIN → MOTOR_NOTE_MIN,  |pos| = MOTOR_POS_MAX → MOTOR_NOTE_MAX.
#   Clamped to the MOTOR_NOTE_MIN..MOTOR_NOTE_MAX range.
MOTOR_POS_MIN  = 0
MOTOR_POS_MAX  = 800
MOTOR_NOTE_MIN = 65
MOTOR_NOTE_MAX = 85

UPDATE_MS = 60          # sensor/telemetry update period
# ───────────────────────────────────────────────────────────────────────────


def build_scale():
    notes = []
    for o in range(OCTAVES):
        for s in PENTATONIC:
            notes.append(ROOT + 12 * o + s)
    return notes

SCALE = build_scale()
N = len(SCALE)


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

light = motor = None

if USE_LIGHT:
    light = make_hub('light')
    print("Connecting Light sensor...")
    light.connect(product_id=COLOR_SENSOR)
    light.feed(UPDATE_MS)

if USE_MOTOR:
    motor = make_hub('motor')
    print("Connecting Single Motor...")
    motor.connect(product_id=SINGLE_MOTOR)
    motor.feed(UPDATE_MS)

print("\n*** LEGO connected — make some noise! ***\n")

# Set the instrument (trombone) on every voice's channel.
if USE_LIGHT:
    program_change(LIGHT_CHANNEL, INSTRUMENT)
if USE_MOTOR:
    program_change(MOTOR_CHANNEL, INSTRUMENT)
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
last_light_note = None
last_motor_note = None

try:
    while True:
        # --- Light sensor → note ---
        if USE_LIGHT:
            reflection = light.data.get('reflection')
            if reflection is None or reflection < LIGHT_GATE:
                target = None
            else:
                idx = int(reflection * (N - 1) / 100)
                target = SCALE[max(0, min(N - 1, idx))]

            if target != last_light_note:
                if last_light_note is not None:
                    note_off(LIGHT_CHANNEL, last_light_note)
                if target is not None:
                    note_on(LIGHT_CHANNEL, target, VELOCITY)
                    print("LIGHT  reflection={:3}  → note {}".format(reflection, target))
                last_light_note = target

        # --- Motor position → note ---
        if USE_MOTOR:
            pos = motor_position(motor)
            if pos is None:
                target = None
            else:
                pos = abs(pos)
                span = MOTOR_POS_MAX - MOTOR_POS_MIN
                note = MOTOR_NOTE_MIN + (pos - MOTOR_POS_MIN) * (MOTOR_NOTE_MAX - MOTOR_NOTE_MIN) / span
                note = int(round(note))
                target = max(MOTOR_NOTE_MIN, min(MOTOR_NOTE_MAX, note))

            if target != last_motor_note:
                if last_motor_note is not None:
                    note_off(MOTOR_CHANNEL, last_motor_note)
                if target is not None:
                    note_on(MOTOR_CHANNEL, target, VELOCITY)
                    print("MOTOR  pos={:5}  → note {}".format(pos, target))
                last_motor_note = target

        time.sleep_ms(UPDATE_MS)

except KeyboardInterrupt:
    print("\nStopping — sending note offs...")
    if last_light_note is not None:
        note_off(LIGHT_CHANNEL, last_light_note)
    if last_motor_note is not None:
        note_off(MOTOR_CHANNEL, last_motor_note)
    time.sleep(0.2)
    if USE_LIGHT:
        try: light.disconnect()
        except: pass
    if USE_MOTOR:
        try: motor.disconnect()
        except: pass
    print("Done.")
