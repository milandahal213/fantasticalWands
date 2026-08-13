# broadcast_probe.py — reverse-engineer what LEGO devices BROADCAST.
#
# Run in Thonny:   import broadcast_probe
#
# It scans continuously and, for every LEGO advertiser (company 0x0397) or any
# device carrying fd02 service data, prints the FULL raw advertising payload —
# but only RE-prints a given device when its bytes CHANGE. So:
#
#   1. Power a Color Sensor grouped to a card. Note its line.
#   2. Hold different colors in front of it — watch which byte(s) change.
#   3. Do the same with a joystick/controller: move it, watch the bytes.
#
# Copy a few of the changed lines back to me and I'll decode the layout, then
# wire the 5x5 matrix (color-sensor color in the middle, joystick L/R on the
# side columns).  Ctrl-C to stop.

import bluetooth
import time
from machine import Pin

LEGO_COMPANY_ID = 0x0397
FD02 = 0xFD02

_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE   = 6


def _ad_structs(adv):
    """Yield (ad_type, payload_bytes) for each AD structure in a raw payload."""
    i = 0
    while i < len(adv):
        length = adv[i]
        if length == 0 or i + length + 1 > len(adv):
            break
        yield adv[i + 1], bytes(adv[i + 2 : i + length + 1])
        i += length + 1


def _lego_identity(adv):
    """(product_id, raw_color, serial) from LEGO mfg data, or None."""
    for ad_type, payload in _ad_structs(adv):
        if ad_type == 0xFF and len(payload) >= 7:
            cid = payload[0] | (payload[1] << 8)
            if cid == LEGO_COMPANY_ID:
                body = payload[2:]
                if len(body) >= 5:
                    pid = (body[0] << 8) | body[1]
                    return pid, body[2], body[3] | (body[4] << 8)
    return None


def _is_interesting(adv):
    """True if this advertiser is a LEGO device or carries fd02 service data."""
    for ad_type, payload in _ad_structs(adv):
        if ad_type == 0xFF and len(payload) >= 2 and \
                (payload[0] | (payload[1] << 8)) == LEGO_COMPANY_ID:
            return True
        # 0x16 = Service Data - 16-bit UUID
        if ad_type == 0x16 and len(payload) >= 2 and \
                (payload[0] | (payload[1] << 8)) == FD02:
            return True
    return False


_last = {}   # addr_str -> last hex string (so we only print on change)


def _irq(event, data):
    if event != _IRQ_SCAN_RESULT:
        return
    addr_type, addr, adv_type, rssi, adv = data
    adv = bytes(adv)
    if not _is_interesting(adv):
        return
    addr_str = ':'.join('%02X' % b for b in addr)
    hexstr = adv.hex()
    if _last.get(addr_str) == hexstr:
        return                       # unchanged — skip so changes stand out
    _last[addr_str] = hexstr

    ident = _lego_identity(adv)
    tag = ''
    if ident:
        pid, raw_color, serial = ident
        tag = ' pid={} rawcolor=0x{:02x} serial={}'.format(pid, raw_color, serial)
    print('{}  rssi={:>4}{}'.format(addr_str, rssi, tag))
    print('    {}'.format(hexstr))


def main():
    # External antenna (same as bledevice.py) so range matches the real wand.
    Pin(3, Pin.OUT).value(0)
    time.sleep_ms(100)
    Pin(14, Pin.OUT).value(1)

    ble = bluetooth.BLE()
    ble.active(True)
    ble.irq(_irq)
    print('Scanning for LEGO / fd02 broadcasters. Change the sensor / move the')
    print('joystick and watch which bytes change. Ctrl-C to stop.\n')
    # active scan, long window, so we also get scan-response payloads
    ble.gap_scan(0, 30000, 30000, True)
    try:
        while True:
            time.sleep_ms(200)
    except KeyboardInterrupt:
        ble.gap_scan(None)
        print('\nstopped.')


main()
