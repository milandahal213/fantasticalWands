"""
SPIKE Prime — raw single-device GATT discovery + notification probe.

Self-contained (no lego_ble.py). Connects to ONE LEGO tech element and
dumps the complete GATT layout, then tries to enable notifications two
different ways and listens. Goal: find out, under the CURRENT firmware,
- what descriptors actually exist (and the real CCCD handle), and
- which subscribe method actually delivers notifications.

Run with ONE tech element powered on. Paste the full output.
"""

import bluetooth
import struct
import time

_SVC_UUID16     = 0xFD02
_SVC_UUID_BYTES = bytes([0x02, 0xFD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
                          0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB])
_CCCD_UUID      = bluetooth.UUID(0x2902)
_NOTIF_UUID     = bluetooth.UUID("0000fd02-0002-1000-8000-00805f9b34fb")
_WRITE_UUID     = bluetooth.UUID("0000fd02-0001-1000-8000-00805f9b34fb")

_IRQ_SCAN_RESULT            = 5
_IRQ_SCAN_DONE              = 6
_IRQ_PERIPHERAL_CONNECT     = 7
_IRQ_PERIPHERAL_DISCONNECT  = 8
_IRQ_GATTC_SERVICE_RESULT   = 9
_IRQ_GATTC_SERVICE_DONE     = 10
_IRQ_GATTC_CHARACTERISTIC_RESULT = 11
_IRQ_GATTC_CHARACTERISTIC_DONE   = 12
_IRQ_GATTC_DESCRIPTOR_RESULT = 13
_IRQ_GATTC_DESCRIPTOR_DONE   = 14
_IRQ_GATTC_READ_RESULT       = 15
_IRQ_GATTC_READ_DONE         = 16
_IRQ_GATTC_WRITE_DONE        = 17
_IRQ_GATTC_NOTIFY            = 18


def _addr_str(a):
    return ":".join("{:02x}".format(b) for b in a)


def _adv_has_lego(adv):
    i = 0
    while i < len(adv):
        ln = adv[i]
        if ln == 0 or i + ln >= len(adv):
            break
        t = adv[i + 1]
        v = adv[i + 2 : i + 1 + ln]
        if t in (0x02, 0x03):
            for j in range(0, len(v) - 1, 2):
                if struct.unpack_from("<H", v, j)[0] == _SVC_UUID16:
                    return True
        elif t in (0x06, 0x07):
            for j in range(0, len(v) - 15, 16):
                if bytes(v[j:j + 16]) == _SVC_UUID_BYTES:
                    return True
        i += 1 + ln
    return False


state = {
    "scan": None, "scan_done": False, "conn": None,
    "svc": None, "svc_done": False,
    "chars": [], "char_done": False,
    "descs": [], "desc_done": False,
    "write_done": None, "notifs": 0,
}


def irq(event, data):
    if event == _IRQ_SCAN_RESULT:
        at, addr, adv_type, rssi, adv = data
        if state["scan"] is None and _adv_has_lego(bytes(adv)):
            state["scan"] = (at, bytes(addr))
            print("  SCAN found", _addr_str(addr))
    elif event == _IRQ_SCAN_DONE:
        state["scan_done"] = True
    elif event == _IRQ_PERIPHERAL_CONNECT:
        ch, at, addr = data
        state["conn"] = ch
        print("  CONNECT handle", ch)
    elif event == _IRQ_PERIPHERAL_DISCONNECT:
        print("  DISCONNECT")
        state["conn"] = None
    elif event == _IRQ_GATTC_SERVICE_RESULT:
        ch, s, e, uuid = data
        print("  SVC start={} end={} uuid={}".format(s, e, uuid))
        if str(uuid) in (str(bluetooth.UUID(_SVC_UUID16)),
                          "0000fd02-0000-1000-8000-00805f9b34fb"):
            state["svc"] = (s, e)
    elif event == _IRQ_GATTC_SERVICE_DONE:
        state["svc_done"] = True
    elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
        ch, dh, vh, props, uuid = data
        print("  CHAR def={} val={} props={} uuid={}".format(dh, vh, props, uuid))
        state["chars"].append((dh, vh, props, str(uuid)))
    elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
        state["char_done"] = True
    elif event == _IRQ_GATTC_DESCRIPTOR_RESULT:
        ch, dh, uuid = data
        print("  DESC handle={} uuid={}".format(dh, uuid))
        state["descs"].append((dh, str(uuid)))
    elif event == _IRQ_GATTC_DESCRIPTOR_DONE:
        state["desc_done"] = True
        print("  DESC_DONE (found {} descriptors)".format(len(state["descs"])))
    elif event == _IRQ_GATTC_WRITE_DONE:
        ch, vh, status = data
        state["write_done"] = (vh, status)
        print("  WRITE_DONE handle={} status={}".format(vh, status))
    elif event == _IRQ_GATTC_NOTIFY:
        ch, vh, payload = data
        state["notifs"] += 1
        raw = bytes(payload)
        print("  NOTIFY handle={} len={} hex={}".format(
            vh, len(raw), " ".join("{:02x}".format(b) for b in raw)))


def wait(fn, t=8000, step=20):
    e = 0
    while not fn():
        time.sleep_ms(step)
        e += step
        if e >= t:
            return False
    return True


ble = bluetooth.BLE()
ble.active(True)
ble.irq(irq)

print("=== Scan ===")
ble.gap_scan(5000, 30000, 30000, True)
wait(lambda: state["scan"] is not None, 6000)
ble.gap_scan(None)
wait(lambda: state["scan_done"], 2000)
if state["scan"] is None:
    print("No hub found."); raise SystemExit

print("=== Connect ===")
ble.gap_connect(state["scan"][0], state["scan"][1])
wait(lambda: state["conn"] is not None)
time.sleep_ms(600)

print("=== Discover services ===")
ble.gattc_discover_services(state["conn"])
wait(lambda: state["svc_done"])
if state["svc"] is None:
    print("FD02 service not found."); raise SystemExit
svc_start, svc_end = state["svc"]

print("=== Discover characteristics ({}..{}) ===".format(svc_start, svc_end))
ble.gattc_discover_characteristics(state["conn"], svc_start, svc_end)
wait(lambda: state["char_done"])

# find notify characteristic
notif_val = notif_def = None
for dh, vh, props, uuid in state["chars"]:
    if uuid == str(_NOTIF_UUID):
        notif_val, notif_def = vh, dh
print("notify char: def={} val={}".format(notif_def, notif_val))

# Try descriptor discovery over a BOUNDED range around the notify char,
# instead of the full 0xFFFF range (which returned nothing before).
lo = notif_def if notif_def not in (None, 65535) else svc_start
hi = (notif_val + 3) if notif_val is not None else svc_start + 10
print("=== Discover descriptors (bounded {}..{}) ===".format(lo, hi))
state["desc_done"] = False
state["descs"] = []
try:
    ble.gattc_discover_descriptors(state["conn"], lo, hi)
    wait(lambda: state["desc_done"], 4000)
except Exception as e:
    print("  descriptor discovery raised:", e)

cccd = None
for dh, uuid in state["descs"]:
    if uuid == str(_CCCD_UUID):
        cccd = dh
if cccd is None and notif_val is not None:
    cccd = notif_val + 1
    print("CCCD not discovered; will try notif_val+1 =", cccd)
else:
    print("CCCD handle =", cccd)

print("=== Subscribe (write 0x0001 to CCCD {}) ===".format(cccd))
state["write_done"] = None
ble.gattc_write(state["conn"], cccd, struct.pack("<H", 1), 1)
wait(lambda: state["write_done"] is not None, 3000)

# Find write characteristic and send program_start + enable_notifications
write_val = None
for dh, vh, props, uuid in state["chars"]:
    if uuid == str(_WRITE_UUID):
        write_val = vh
print("=== Send program_start + enable_notifications via handle {} ===".format(write_val))
ble.gattc_write(state["conn"], write_val, bytes([32, 0]), 0)      # PROGRAM_FLOW START
time.sleep_ms(100)
ble.gattc_write(state["conn"], write_val, bytes([40, 50, 0]), 0)  # NOTIFY_REQUEST 50ms

print("=== Listen 6 s ===")
for _ in range(60):
    time.sleep_ms(100)

print("=== RESULT: received {} notification(s) ===".format(state["notifs"]))
ble.gap_disconnect(state["conn"])
time.sleep_ms(300)
print("Done.")
