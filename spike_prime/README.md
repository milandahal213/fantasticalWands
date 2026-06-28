# SPIKE Prime → LEGO tech elements (BLE)

MicroPython code for connecting a **LEGO SPIKE Prime** hub (as a BLE central)
to the new LEGO Education **tech elements** — standalone Bluetooth devices
(Single Motor, Color Sensor, Controller, …) that advertise service `0xFD02`
and speak a custom RPC protocol.

Runs on the SPIKE Prime's **standard LEGO firmware** (the one with the
`bluetooth`, `motor`, `color_sensor` modules) — **not** Pybricks.

## Key finding: one connection at a time

**The SPIKE Prime firmware supports only ONE simultaneous BLE central
connection to these tech elements.** The first connects fine; a second
`gap_connect` returns a spurious `ENOTCONN` and a phantom handle `0` whose
GATT operations all fail with `EINVAL`. This is compiled into the hub's BLE
stack — there is no runtime setting to change it.

| Controller        | Connect to tech elements | Multiple at once |
|-------------------|--------------------------|------------------|
| **SPIKE Prime**   | ✅ yes (one)             | ❌ no             |
| **ESP32-C6**      | ✅ yes                   | ✅ yes (proven)   |
| **Pybricks**      | ❌ no (no generic BLE central API) | — |

➡️ **For multiple tech elements at once, use the ESP32-C6 build in
[`../lego_education/`](../lego_education/).**

## Files

| File | What it does |
|------|--------------|
| `lego_ble.py` | The driver: scan, connect, RPC message encode, notification parse. Import this. |
| `color_sensor_read.py` | **Working single-device demo** — connect to one Color Sensor and print live readings. |
| `connection_test.py` | Minimal single-device connect + info request + 5 s notification dump. |
| `color_motor_control.py` | ⚠️ Needs TWO connections — **does not work on SPIKE**, kept for ESP32-C6. |
| `discovery_test.py` | Raw single-device GATT probe. Use to **verify a hub is healthy** (see below). |
| `two_device_gatt_test.py` | Raw probe proving the two-connection limit. |
| `multi_connect_test.py` | Earlier raw connect/disconnect probe. |
| `ble_debug.py` | Verbose raw BLE event logger. |

## Usage (single tech element)

1. Power on one tech element (e.g. a Color Sensor).
2. Copy `lego_ble.py` **and** your script onto the hub's filesystem (not just
   the editor buffer — `import lego_ble` reads the on-device copy).
3. Run `color_sensor_read.py`.

```python
from lego_ble import LegoDevice, COLOR_SENSOR_NOTIFICATION

def on_notif(items):
    for n in items:
        if n["type"] == COLOR_SENSOR_NOTIFICATION:
            print(n["color"], n["reflected"])

dev = LegoDevice(notification_callback=on_notif)
dev.scan_and_connect()
dev.program_start()
dev.enable_notifications(100)
```

## SPIKE-specific gotchas (learned the hard way)

- **Service UUID is reported 16-bit** as `UUID(0xfd02)`, not the full 128-bit
  form. The driver matches both.
- **Descriptor discovery over the full range fails.** Discovering descriptors
  to end-handle `0xFFFF` returns nothing; the driver uses a bounded range
  around the notify characteristic. The CCCD is `notify_value_handle + 1`.
- **A hub that ran Pybricks may not fully restore SPIKE firmware.** Symptom:
  broken GATT — `discovery_test.py` finds 0 descriptors and the CCCD write
  reports handle `65535`, and no notifications arrive. A healthy hub finds 5
  descriptors and gets `WRITE_DONE handle=15 status=0`. **Run
  `discovery_test.py` to check a hub before blaming the code.**
- **Files must be on the hub's filesystem.** Running a script from the editor
  doesn't update an imported module on the device.

## For the classroom

A program running **standalone on the hub** (downloaded, launched from a
button — not tethered to a computer) still only gets one tech-element
connection; the limit is the hub firmware, not the dev tether. Plan one tech
element per SPIKE hub, or use an ESP32-C6 when several elements must be driven
together.
