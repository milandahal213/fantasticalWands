"""
BLE diagnostic — run this to see exactly what the hub sends.
Copy to ESP32-C6 and run it. It prints raw hex for every IRQ event.
"""

import bluetooth
import struct
import time

_SVC_UUID   = bluetooth.UUID("0000FD02-0000-1000-8000-00805F9B34FB")
_WRITE_UUID = bluetooth.UUID("0000FD02-0001-1000-8000-00805F9B34FB")
_NOTIF_UUID = bluetooth.UUID("0000FD02-0002-1000-8000-00805F9B34FB")
_SVC_UUID_BYTES = bytes([0x02, 0xFD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
                          0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB])
_SVC_UUID16 = 0xFD02

_IRQ_SCAN_RESULT                 = 5
_IRQ_SCAN_DONE                   = 6
_IRQ_PERIPHERAL_CONNECT          = 7
_IRQ_PERIPHERAL_DISCONNECT       = 8
_IRQ_GATTC_SERVICE_RESULT        = 9
_IRQ_GATTC_SERVICE_DONE          = 10
_IRQ_GATTC_CHARACTERISTIC_RESULT = 11
_IRQ_GATTC_CHARACTERISTIC_DONE   = 12
_IRQ_GATTC_DESCRIPTOR_RESULT     = 13
_IRQ_GATTC_DESCRIPTOR_DONE       = 14
_IRQ_GATTC_READ_RESULT           = 15
_IRQ_GATTC_READ_DONE             = 16
_IRQ_GATTC_WRITE_DONE            = 17
_IRQ_GATTC_NOTIFY                = 18

def _adv_has_lego_service(adv_data):
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0 or i + length >= len(adv_data):
            break
        ad_type = adv_data[i + 1]
        ad_val  = adv_data[i + 2 : i + 1 + length]
        if ad_type in (0x02, 0x03):
            for j in range(0, len(ad_val) - 1, 2):
                if struct.unpack_from("<H", ad_val, j)[0] == _SVC_UUID16:
                    return True
        elif ad_type in (0x06, 0x07):
            for j in range(0, len(ad_val) - 15, 16):
                if bytes(ad_val[j : j + 16]) == _SVC_UUID_BYTES:
                    return True
        i += 1 + length
    return False

ble = bluetooth.BLE()
ble.active(True)

scan_result   = None
scan_done     = False
conn_handle   = None
svc_start     = None
svc_end       = None
write_handle  = None
notif_handle  = None
notif_def     = None
cccd_handle   = None
svc_done      = False
char_done     = False
desc_done     = False
all_chars     = []  # (def_handle, value_handle, uuid)
all_descs     = []  # (dsc_handle, uuid)

def irq(event, data):
    global scan_result, scan_done, conn_handle
    global svc_start, svc_end, svc_done
    global write_handle, notif_handle, notif_def, char_done
    global cccd_handle, desc_done

    if event == _IRQ_SCAN_RESULT:
        addr_type, addr, adv_type, rssi, adv_data = data
        if scan_result is None and _adv_has_lego_service(bytes(adv_data)):
            scan_result = (addr_type, bytes(addr))
            print("SCAN: found LEGO hub addr_type={} addr={}".format(
                addr_type, ':'.join('{:02x}'.format(b) for b in addr)))

    elif event == _IRQ_SCAN_DONE:
        scan_done = True

    elif event == _IRQ_PERIPHERAL_CONNECT:
        conn_handle, addr_type, addr = data
        print("CONNECT: conn_handle={}".format(conn_handle))

    elif event == _IRQ_PERIPHERAL_DISCONNECT:
        print("DISCONNECT")
        conn_handle = None

    elif event == _IRQ_GATTC_SERVICE_RESULT:
        ch, start, end, uuid = data
        print("SERVICE: start={} end={} uuid={}".format(start, end, uuid))
        if uuid == _SVC_UUID:
            svc_start = start
            svc_end   = end

    elif event == _IRQ_GATTC_SERVICE_DONE:
        print("SERVICE_DONE: svc_start={} svc_end={}".format(svc_start, svc_end))
        svc_done = True

    elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
        ch, def_h, val_h, props, uuid = data
        print("CHAR: def_handle={} value_handle={} props={} uuid={}".format(
            def_h, val_h, props, uuid))
        all_chars.append((def_h, val_h, uuid))
        if uuid == _WRITE_UUID:
            write_handle = val_h
        elif uuid == _NOTIF_UUID:
            notif_handle = val_h
            notif_def    = def_h

    elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
        print("CHAR_DONE: write_handle={} notif_handle={} notif_def={}".format(
            write_handle, notif_handle, notif_def))
        char_done = True

    elif event == _IRQ_GATTC_DESCRIPTOR_RESULT:
        ch, dsc_h, uuid = data
        print("DESC: dsc_handle={} uuid={}".format(dsc_h, uuid))
        all_descs.append((dsc_h, uuid))
        if uuid == bluetooth.UUID(0x2902):
            cccd_handle = dsc_h

    elif event == _IRQ_GATTC_DESCRIPTOR_DONE:
        print("DESC_DONE: cccd_handle={}".format(cccd_handle))
        desc_done = True

    elif event == _IRQ_GATTC_WRITE_DONE:
        ch, val_h, status = data
        print("WRITE_DONE: value_handle={} status={}".format(val_h, status))

    elif event == _IRQ_GATTC_NOTIFY:
        ch, val_h, notify_data = data
        raw = bytes(notify_data)
        print("NOTIFY: handle={} len={} hex={}".format(
            val_h, len(raw), ' '.join('{:02x}'.format(b) for b in raw)))

    else:
        print("IRQ event={}".format(event))

ble.irq(irq)

def wait(flag_fn, timeout_ms=8000, poll_ms=20):
    elapsed = 0
    while not flag_fn():
        time.sleep_ms(poll_ms)
        elapsed += poll_ms
        if elapsed >= timeout_ms:
            raise OSError("Timeout")

# 1. Scan
print("\n=== Scanning ===")
ble.gap_scan(10000, 30000, 30000, True)
wait(lambda: scan_result is not None or scan_done, 10000)
ble.gap_scan(None)
if not scan_result:
    raise OSError("No hub found")

# 2. Connect
print("\n=== Connecting ===")
ble.gap_connect(scan_result[0], scan_result[1])
wait(lambda: conn_handle is not None)

# 3. Discover services
print("\n=== Service discovery ===")
ble.gattc_discover_services(conn_handle)
wait(lambda: svc_done)

# 4. Discover characteristics
print("\n=== Characteristic discovery ===")
ble.gattc_discover_characteristics(conn_handle, svc_start, svc_end)
wait(lambda: char_done)

# 5. Discover ALL descriptors in the whole service range
print("\n=== Descriptor discovery (full service range) ===")
ble.gattc_discover_descriptors(conn_handle, svc_start, svc_end)
wait(lambda: desc_done)

# 6. Try to subscribe — use cccd if found, else try notif_handle + 1
if cccd_handle is not None:
    print("\n=== Writing CCCD={} to enable notifications ===".format(cccd_handle))
    ble.gattc_write(conn_handle, cccd_handle, struct.pack("<H", 1), 1)
else:
    print("\n=== CCCD not found! Trying notif_handle+1={} ===".format(notif_handle + 1))
    ble.gattc_write(conn_handle, notif_handle + 1, struct.pack("<H", 1), 1)

time.sleep_ms(200)

# 7. Send program start + enable notifications RPC
print("\n=== Sending program_start + enable_notifications ===")
ble.gattc_write(conn_handle, write_handle, bytes([32, 0]), 0)  # PROGRAM_FLOW_NOTIFICATION, START
time.sleep_ms(100)
ble.gattc_write(conn_handle, write_handle, bytes([40, 50, 0]), 0)  # DEVICE_NOTIFICATION_REQUEST, 50ms

# 8. Listen for 10 seconds and print everything
print("\n=== Listening for 10 seconds — watching for NOTIFY events ===")
for i in range(100):
    time.sleep_ms(100)

print("\n=== Done ===")
print("All descriptors found:", all_descs)
ble.gap_disconnect(conn_handle)
