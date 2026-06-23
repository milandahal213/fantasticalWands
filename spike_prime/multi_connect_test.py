"""
SPIKE Prime — BLE multi-connection diagnostic.

QUESTION THIS ANSWERS:
    Can the SPIKE Prime hold TWO simultaneous BLE central connections
    to LEGO hubs at the same time?

This is self-contained (does NOT use lego_ble.py) and uses only raw
bluetooth calls, so our library is not a variable. Every BLE event is
logged. It scans ONCE for both hubs, waits for the scan to fully stop,
then connects to each in turn while keeping the first open.

HOW TO RUN:
    1. Power on BOTH LEGO hubs (e.g. Single Motor + Color Sensor).
    2. Copy this file to the SPIKE Prime and run it.
    3. Paste the entire output back.

NOTE: If you are running this code over a *Bluetooth* link to the SPIKE
Prime (rather than USB), that link may already consume one BLE slot and
skew the result. Prefer a USB cable for this test.
"""

import bluetooth
import struct
import time

# LEGO service UUID — 16-bit form (0xFD02) and 128-bit byte form
_SVC_UUID16     = 0xFD02
_SVC_UUID_BYTES = bytes([0x02, 0xFD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
                          0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB])

_IRQ_SCAN_RESULT           = 5
_IRQ_SCAN_DONE             = 6
_IRQ_PERIPHERAL_CONNECT    = 7
_IRQ_PERIPHERAL_DISCONNECT = 8


def _addr_str(addr):
    return ":".join("{:02x}".format(b) for b in addr)


def _adv_has_lego_service(adv):
    i = 0
    while i < len(adv):
        ln = adv[i]
        if ln == 0 or i + ln >= len(adv):
            break
        ad_type = adv[i + 1]
        ad_val  = adv[i + 2 : i + 1 + ln]
        if ad_type in (0x02, 0x03):              # 16-bit service UUIDs
            for j in range(0, len(ad_val) - 1, 2):
                if struct.unpack_from("<H", ad_val, j)[0] == _SVC_UUID16:
                    return True
        elif ad_type in (0x06, 0x07):            # 128-bit service UUIDs
            for j in range(0, len(ad_val) - 15, 16):
                if bytes(ad_val[j : j + 16]) == _SVC_UUID_BYTES:
                    return True
        i += 1 + ln
    return False


# ── Shared state ──────────────────────────────────────────────────────────────
found       = []   # list of (addr_type, addr_bytes), LEGO hubs only, deduped
scan_done   = False
connections = {}   # conn_handle -> addr_bytes (currently-live connections)


def irq(event, data):
    global scan_done
    if event == _IRQ_SCAN_RESULT:
        addr_type, addr, adv_type, rssi, adv = data
        if _adv_has_lego_service(bytes(adv)):
            a = bytes(addr)
            if not any(a == known for (_, known) in found):
                found.append((addr_type, a))
                print("  [SCAN] LEGO hub:", _addr_str(a),
                      "type", addr_type, "rssi", rssi)

    elif event == _IRQ_SCAN_DONE:
        scan_done = True
        print("  [SCAN_DONE]")

    elif event == _IRQ_PERIPHERAL_CONNECT:
        conn_handle, addr_type, addr = data
        connections[conn_handle] = bytes(addr)
        print("  [CONNECT] handle", conn_handle, "addr", _addr_str(addr),
              "-> live connections:", len(connections))

    elif event == _IRQ_PERIPHERAL_DISCONNECT:
        conn_handle, addr_type, addr = data
        connections.pop(conn_handle, None)
        print("  [DISCONNECT] handle", conn_handle,
              "-> live connections:", len(connections))

    else:
        print("  [IRQ] event", event)


def wait(flag_fn, timeout_ms=8000, step_ms=20):
    elapsed = 0
    while not flag_fn():
        time.sleep_ms(step_ms)
        elapsed += step_ms
        if elapsed >= timeout_ms:
            return False
    return True


ble = bluetooth.BLE()
ble.active(True)
ble.irq(irq)

print("=== Step 1: scan 6s for LEGO hubs (power on BOTH now) ===")
found.clear()
scan_done = False
ble.gap_scan(6000, 30000, 30000, True)   # active scan, full 6s duration
wait(lambda: scan_done, 8000)
print("Discovered", len(found), "LEGO hub(s).")

if len(found) == 0:
    print("No hubs found — nothing to test. Power them on and retry.")
    raise SystemExit

# ── Step 2: connect to hub 1 ──────────────────────────────────────────────────
print("\n=== Step 2: connect to hub 1 ===")
at1, addr1 = found[0]
try:
    ble.gap_connect(at1, addr1)
except Exception as e:
    print("gap_connect(hub1) raised:", e)
ok1 = wait(lambda: len(connections) >= 1, 8000)
print("Hub 1 connected:", ok1, "| live connections:", len(connections))
time.sleep_ms(1000)   # let the first link settle

# ── Step 3: connect to hub 2 while hub 1 stays connected ──────────────────────
if len(found) >= 2:
    print("\n=== Step 3: connect to hub 2 (hub 1 still connected) ===")
    at2, addr2 = found[1]
    try:
        ble.gap_connect(at2, addr2)
    except Exception as e:
        print("gap_connect(hub2) raised:", e)
    ok2 = wait(lambda: len(connections) >= 2, 8000)
    print("Hub 2 connected:", ok2, "| live connections:", len(connections))
else:
    print("\n=== Step 3 skipped: only 1 hub found ===")
    print("Power on a second hub and rerun to test two connections.")

time.sleep_ms(2000)

# ── Result ────────────────────────────────────────────────────────────────────
print("\n=== RESULT ===")
print("Simultaneous live connections:", len(connections))
if len(connections) >= 2:
    print("PASS — SPIKE Prime CAN hold multiple BLE connections.")
    print("       The ENOTCONN was our library's scan/connect sequencing,")
    print("       not a hardware limit. We can fix lego_ble.py.")
elif len(connections) == 1:
    print("INCONCLUSIVE/FAIL — held only 1 connection.")
    print("       Either a real limit, or hub 2 connect failed above.")
    print("       Check the Step 3 log lines for why.")
else:
    print("FAIL — no connections held. See logs above.")

# ── Cleanup ───────────────────────────────────────────────────────────────────
for ch in list(connections.keys()):
    try:
        ble.gap_disconnect(ch)
    except Exception:
        pass
time.sleep_ms(500)
print("Done.")
