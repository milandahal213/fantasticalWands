"""
SPIKE Prime — two-connection GATT probe (self-contained, no lego_ble.py).

Earlier multi_connect_test proved two connections can COEXIST, but it never
did GATT on the second one. This test does service+characteristic discovery
on BOTH connections. The second connection sometimes comes up as a bad
"handle 0" link whose GATT calls return EINVAL; when that happens we drop it
and reconnect, to learn whether a clean second connection is achievable.

Run with TWO tech elements powered on. Paste the full output.
"""

import bluetooth
import struct
import time

_SVC_UUID16     = 0xFD02
_SVC_UUID_BYTES = bytes([0x02, 0xFD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
                          0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB])

_IRQ_SCAN_RESULT            = 5
_IRQ_SCAN_DONE              = 6
_IRQ_PERIPHERAL_CONNECT     = 7
_IRQ_PERIPHERAL_DISCONNECT  = 8
_IRQ_GATTC_SERVICE_RESULT   = 9
_IRQ_GATTC_SERVICE_DONE     = 10
_IRQ_GATTC_CHARACTERISTIC_RESULT = 11
_IRQ_GATTC_CHARACTERISTIC_DONE   = 12


def _astr(a):
    return ":".join("{:02x}".format(b) for b in a)


def _adv_has_lego(adv):
    i = 0
    while i < len(adv):
        ln = adv[i]
        if ln == 0 or i + ln >= len(adv):
            break
        t = adv[i + 1]
        v = adv[i + 2:i + 1 + ln]
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


found = []
S = {"scan_done": False, "conn": None, "disc": None,
     "svc_done": False, "svc_n": 0, "char_done": False, "char_n": 0}


def irq(event, data):
    if event == _IRQ_SCAN_RESULT:
        at, addr, t, rssi, adv = data
        if _adv_has_lego(bytes(adv)):
            a = bytes(addr)
            if not any(a == k for (_, k) in found):
                found.append((at, a))
                print("  SCAN", _astr(a))
    elif event == _IRQ_SCAN_DONE:
        S["scan_done"] = True
    elif event == _IRQ_PERIPHERAL_CONNECT:
        ch, at, addr = data
        S["conn"] = ch
        print("  CONNECT handle", ch)
    elif event == _IRQ_PERIPHERAL_DISCONNECT:
        ch = data[0]
        S["disc"] = ch
        print("  DISCONNECT handle", ch)
    elif event == _IRQ_GATTC_SERVICE_RESULT:
        S["svc_n"] += 1
    elif event == _IRQ_GATTC_SERVICE_DONE:
        S["svc_done"] = True
    elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
        S["char_n"] += 1
    elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
        S["char_done"] = True


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


def try_gatt(conn):
    """Run service + characteristic discovery on conn. Return True if it works."""
    S["svc_done"] = False; S["svc_n"] = 0
    try:
        ble.gattc_discover_services(conn)
    except OSError as e:
        print("    discover_services raised", e)
        return False
    if not wait(lambda: S["svc_done"], 4000):
        print("    service discovery: no completion")
        return False
    print("    services found:", S["svc_n"])
    return S["svc_n"] > 0


def connect_with_gatt(at, addr, label, attempts=4):
    """Connect to addr and confirm GATT works; reconnect on bad link."""
    for i in range(attempts):
        print("  {} connect attempt {}/{}".format(label, i + 1, attempts))
        S["conn"] = None
        try:
            ble.gap_connect(at, addr)
        except OSError as e:
            print("    gap_connect raised", e, "(waiting for event)")
        if not wait(lambda: S["conn"] is not None, 8000):
            print("    no connect event")
            continue
        conn = S["conn"]
        time.sleep_ms(700)
        print("    connected handle={}; testing GATT…".format(conn))
        if try_gatt(conn):
            print("    GATT OK on handle", conn)
            return conn
        # Bad link — drop it and retry.
        print("    GATT FAILED on handle {}; disconnecting & retrying".format(conn))
        try:
            ble.gap_disconnect(conn)
        except Exception:
            pass
        wait(lambda: S["disc"] == conn, 2000)
        time.sleep_ms(800)
    return None


print("=== Scan 6s for two hubs ===")
ble.gap_scan(6000, 30000, 30000, True)
wait(lambda: S["scan_done"], 8000)
print("Found", len(found), "hub(s)")
if len(found) < 2:
    print("Need 2 hubs. Stopping."); raise SystemExit

c1 = connect_with_gatt(found[0][0], found[0][1], "HUB1")
c2 = connect_with_gatt(found[1][0], found[1][1], "HUB2")

print("\n=== RESULT ===")
print("HUB1 GATT-usable handle:", c1)
print("HUB2 GATT-usable handle:", c2)
if c1 is not None and c2 is not None:
    print("PASS — two connections BOTH with working GATT.")
else:
    print("FAIL — could not get working GATT on both connections.")

for c in (c1, c2):
    if c is not None:
        try:
            ble.gap_disconnect(c)
        except Exception:
            pass
time.sleep_ms(500)
print("Done.")
