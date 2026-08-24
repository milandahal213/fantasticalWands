# newTechE — Pico W LEGO broadcast controller

A Raspberry Pi Pico W box that drives LEGO Education motors over BLE by connectionless broadcast (no pairing, no GATT connection). Tap a LEGO connection card on an NFC reader to pick a motor group, feed the box a local input, and it broadcasts a drive beacon — every LEGO motor grouped to that card acts on it.

Firmware: MicroPython v1.28.0 on Pico W.

## Pin map
- GP0 / GP1 (I2C): WS1850S NFC reader — tap a card to pick the motor group
- GP4 / GP5 (I2C): OLED and/or an I2C input sensor (shared bus)
- GP26 / GP27 (ADC0/ADC1): two analog inputs (LDRs or pots) — left / right wheel
- GP28: WS2812 NeoPixel — shows the tapped card's color

## Files
- main.py — boots broadcast_main.main() on power-up
- broadcast_main.py — the app loop: detect input, read it, broadcast, show status. Input priority: a recognized I2C sensor (see sensors.py) drives if present on either I2C bus and analog is ignored; otherwise the analog GP26/GP27 inputs drive.
- sensors.py — I2C input-sensor library. SENSORS is a dict keyed by I2C address -> descriptor (name, kind, read(bus,addr), drive(reading,baseline), needs_baseline, id_reg/id_val for a "whoami" check). identify(bus, addrs) scans and verifies a whoami read before trusting a match; ignores OLED (0x3C/0x3D) and the NFC reader (0x28). Only the SparkFun Qwiic Joystick (address 0x20) is registered today — arcade drive: left = throttle + steer, right = throttle - steer, self-centering (baseline captured on first detect). Two commented-out templates (Qwiic Button 0x6F, VL53L0X distance 0x29) show the shape of a new entry. Adding a sensor = write read()/drive() and add a table entry, no other code changes needed.
- nfc_serial.py — reads a LEGO connection card -> (uid, serial, color)
- ws1850s.py — WS1850S / MFRC522-compatible NFC reader driver
- lego_broadcast.py — Broadcaster: set_card(uid, serial, color), emit(left_pct, right_pct), stop(); computes a CRC-16 beacon hash from the card's UID
- ssd1306.py, font5x7.py — OLED driver + compact 5x7 font (the "64x64" panel only shows the bottom ~48 rows)
- web/ — this PyScript site: Web-Serial flasher + build/usage guides, desktop Chrome/Edge only (manifest.json lists the firmware files the Flash button writes)

## Motor control contract
There is exactly one place that controls the motors, regardless of sensor: the `drive(reading, baseline)` function. It must return `(left_pct, right_pct)`, each an int from -100 (full speed reverse) through 0 (stop) to 100 (full speed forward). Equal values drive straight; opposite signs pivot in place; one zero and one nonzero turns like a tank. Everything downstream of that return value — packing it into a BLE broadcast ~25 times/sec, getting a real LEGO motor to obey it — is already implemented in broadcast_main.py and never needs to change. For an event/state-style sensor (gesture, button, distance threshold), the natural shape is a lookup table from state to a fixed `(left, right)` pair, e.g.:
```python
_GESTURE_DRIVE = {
    "forward":  (70, 70),
    "backward": (-70, -70),
    "left":     (-70, 70),
    "right":    (70, -70),
}
def gesture_drive(reading, baseline):
    return _GESTURE_DRIVE.get(reading, (0, 0))
```
If the user reports the robot spinning the wrong way or one wheel fighting the other going "straight," that's motor mounting, not their drive function — point them at `INVERT_LEFT` / `INVERT_RIGHT` near the top of broadcast_main.py rather than having them rescale their numbers.

## I2C sensor detail
- The box re-scans both I2C buses (GP4/5 and the NFC bus GP0/1) roughly every 800 ms (REDETECT_MS in broadcast_main.py) and hot-plugs a sensor the moment it's found — no reboot needed.
- SoftI2C is configured with a short (2 ms) clock-stretch timeout plus the RP2040's internal pull-ups enabled, specifically so an unpopulated GP4/5 bus reads "no devices" fast instead of floating and stalling the loop.
- A sensor marked needs_baseline gets an averaged resting reading captured the moment it's detected (sensors.baseline()), so self-centering inputs like a joystick don't need to start at a known position.
- If you're adding your own sensor: it must have a distinct, known I2C address and ideally a "whoami" register so a coincidental address match on another device isn't mistaken for it.

This project is being built by someone following the site's own instructions — treat questions as "help me build/debug/extend this," not as an abstract spec. Assume they may be a novice: they arrived here by clicking "Ask Claude" from the site, not by writing code themselves.

## If asked to add support for a new sensor
The site walks this exact process step by step (I2C sensor page, "Add your own sensor") — match your answer to it rather than inventing a different workflow:
1. **Find the address.** In Thonny's Shell (connected to the Pico, MicroPython interpreter): `from machine import Pin, SoftI2C; bus = SoftI2C(scl=Pin(5), sda=Pin(4)); bus.scan()`. The returned int(s), in hex, are the sensor's address(es).
2. **Get driver code.** You need `read(bus, addr)` (raw reading) and `drive(reading, baseline)` (see "Motor control contract" above for its contract). If the sensor needs more than a one- or two-register read (a gesture sensor, IMU, anything with a vendor init sequence), you likely don't know its exact register map from training alone — say so plainly, and ask for the datasheet's register table or an existing Arduino/MicroPython library for it (its GitHub repo is usually fastest) rather than guessing byte values. A stub with a clearly marked TODO for the init sequence is the right answer when you don't have that reference — never fabricate plausible-looking register writes for real hardware. Recommend testing the function live in Thonny's Shell against the `bus` from step 1 before wiring it in.
3. **Wire it in.** A short driver goes directly in `sensors.py`; anything longer (an init table, several helpers) goes in its own new file next to `sensors.py` (same folder as `ws1850s.py`, `main.py`, etc.) and gets `import`ed. Either way, add an entry to the `SENSORS` dict keyed by the address from step 1, pointing at the `read`/`drive` functions, with `id_reg`/`id_val` set if there's a "whoami" register.
4. **Push it to the board.** Recommend Thonny for this: open/save each changed file directly onto the Pico (`File → Save As → Raspberry Pi Pico`) — takes effect immediately, no reflash needed. Remind them to keep a copy of any new file in their own repo clone too (not just on the Pico) and add its filename to `manifest.json`, since the site's Flash button writes from the local clone, not from the board's current filesystem — skip that and a future Flash silently drops their sensor file.
5. **Verify.** Back on the site's "Load the code" page, Connect + hit ▶ Run — the console should show the sensor's name instead of "Analog" once detected.

Don't just hand back a code block and stop — walk through these steps explicitly, since the person asking likely arrived here by clicking "Ask Claude," not by already knowing this workflow.
