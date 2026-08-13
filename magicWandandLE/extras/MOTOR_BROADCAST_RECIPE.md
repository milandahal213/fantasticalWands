# Driving a LEGO Education motor from any device — broadcast recipe

Make *any* device control a LEGO Education motor with **no pairing and no
connection**, the way the wand does in `magicWandandLE/lib/legocast.py`. This is the one-page
recipe to recreate it with a different sender (another micro, a phone bridge, a
Pi, etc.).

## The idea

LEGO Education bricks that share a **Connection Card** form a group and talk
over **connectionless BLE advertising** (service UUID `0xFD02`). A controller or
sensor just broadcasts its state; motors in the same group listen and act. So
any device that can *transmit a BLE advertisement* can impersonate a sender and
drive a grouped motor.

## What you need

- **A transmitter that can broadcast custom advertisements:** Pico W / ESP32
  (MicroPython `bluetooth.BLE().gap_advertise`), or Linux/BlueZ (HCI).
  **macOS cannot** (bleak scans/connects only).
- The **target motor tapped with a Connection Card**.
- That card's **NFC UID (7 bytes)**, **colour code**, and **serial** (0–9999).

## Beacon — 12 bytes of `0xFD02` service data

| byte | meaning |
|---|---|
| 0 | device-type tag — `0x02` colour sensor, `0x03` controller, `0x04` used here for the double motor |
| 1 | card colour (raw byte) |
| 2 | card hash hi  ← **required** |
| 3–4 | card serial, little-endian |
| 5 | command / left value |
| 6 | command / right value |
| 7 | card hash lo  ← **required** |
| 8 | constant (`0x80`) |
| 9–11 | rolling counter — **must keep advancing** or the motor treats packets as stale |

Wrapped as an AD payload: `02 01 06` (flags) + `len 16 02 FD <12 payload bytes>`.

## Step 1 — get the card identity

Read the card's NFC **UID** (7 bytes), colour, and serial. The colour + serial
are the group address; the UID feeds the hash.

## Step 2 — compute the hash (`byte2:byte7`)

It's a CRC-16 of the UID — polynomial `0x0001` (x¹⁶+1, i.e. a 16-bit XOR fold),
reflected in/out, init 0, big-endian. The **motor validates it**, so it must be
right.

```python
def card_hash(uid):                     # uid = 7 raw UID bytes
    def refl(b, w): return int(f"{b:0{w}b}"[::-1], 2)
    crc = 0
    for byte in uid:
        crc ^= refl(byte, 8) << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x0001) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    crc = refl(crc, 16)
    return (crc >> 8) & 0xFF, crc & 0xFF   # (byte2, byte7)
```

## Step 3 — encode your control into `b5`/`b6`

Depends on the device-type tag you send:

- **Controller (`0x03`)** — motor reads the **low nibble** of `b5` (right) and
  `b6` (left) as a signed speed: `0` stop, `1/2/3` forward, `F/E/D` reverse.
  7 states each; high nibble ignored.
- **Type `0x04` (double motor drive)** — `b5`/`b6` are per-wheel speeds; encode
  the desired speed per wheel (start with signed 8-bit: `0x00` stop, `0x01..0x7f`
  forward, `0x80..0xff` reverse — verify against your motor).

For differential drive: `left = throttle + steer`, `right = throttle - steer`,
and negate one wheel if the motors are mounted mirror-image.

## Step 4 — broadcast continuously

```python
import bluetooth, time
ble = bluetooth.BLE(); ble.active(True)
counter = 0
COLOR, SERIAL = 0x02, 6044
B2, B7 = card_hash(uid)                 # from step 2

def beacon(b5, b6, ctr):
    svc = bytes([0x04, COLOR, B2, SERIAL & 0xFF, (SERIAL >> 8) & 0xFF,
                 b5, b6, B7, 0x80,
                 (ctr >> 16) & 0xFF, (ctr >> 8) & 0xFF, ctr & 0xFF])
    sd  = bytes([0x16, 0x02, 0xFD]) + svc
    return bytes([0x02, 0x01, 0x06]) + bytes([len(sd)]) + sd

while True:
    b5, b6 = read_your_control()        # buttons, joystick, accelerometer...
    ble.gap_advertise(None)
    ble.gap_advertise(100_000, adv_data=beacon(b5, b6, counter), connectable=False)
    counter = (counter + 0x00B300) & 0xFFFFFF   # keep it moving
    time.sleep_ms(80)
```

## Gotchas

- **Hash is required** — right serial + wrong `byte2`/`byte7` is ignored.
- **Counter must advance** every packet, or the motor stops (treats repeats as stale).
- **Group = colour + serial** — must match the card tapped on the motor.
- **Only the type tag changes the interpretation** of `b5`/`b6`; sweep byte values
  on a new device type to learn its command mapping.
- **You never need the physical card** — read its UID/colour/serial once (or off any
  device already wearing it) and you can fabricate the beacon forever.

Reference implementations: `magicWandandLE/lib/legocast.py` (ESP32-C6 wand) and
`newTechE/lego_broadcast.py` (Pico W), both in this repo.
