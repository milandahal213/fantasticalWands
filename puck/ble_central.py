"""
ble_central.py — puck BLE transport built on the repo's raw-bluetooth driver.

Wraps lib/bledevice.py (BLEDevice): no aioble required. Synchronous and
IRQ-driven, matching how the wand connects to LEGO hardware. Discovers all
LEGO devices wearing the puck's card (color + number), connects the ones the
behavior needs into named slots, and feeds notifications into LegoDevice models.
"""

import time

from bledevice import BLEDevice
import lego_ble as L


class PuckBLE:
    def __init__(self):
        self.ble = BLEDevice()
        self.devices = {}      # slot -> LegoDevice
        self._seq = 0

    def next_slot(self):
        self._seq += 1
        return "d%d" % self._seq

    def discover_matching(self, match_color, number, duration_ms=3000,
                          idle_cb=None, progress_cb=None):
        """Return [{'addr_type','addr','kind'}] for LEGO devices whose card
        matches (color AND number) and whose product maps to a known kind.

        idle_cb() runs ~20x/sec during the scan (drive a breathing LED);
        progress_cb(result) runs when a matching device appears (flash)."""
        results = self.ble.discover(duration_ms=duration_ms,
                                    card_color=match_color, card_serial=number,
                                    idle_cb=idle_cb, progress_cb=progress_cb)
        out = []
        for r in results:
            kind = L.PRODUCT_KIND.get(r["product_id"])
            if kind:
                out.append({"addr_type": r["addr_type"], "addr": r["addr"], "kind": kind})
        return out

    def connect(self, addr_type, addr, kind, timeout_ms=8000):
        """Connect to one device, run the InfoRequest handshake, enable
        notifications. Returns (slot, LegoDevice) or (None, None)."""
        slot = self.next_slot()
        dev = L.LegoDevice(kind, L.KIND_LABEL.get(kind, kind),
                           lambda data, s=slot: self.ble.write(s, data))
        # notifications -> parse -> update device state (set before connect_to,
        # which preserves an already-registered callback for the slot)
        self.ble.set_callback(
            slot, lambda nd, d=dev: d.apply(L.parse_notification(bytes(nd))))
        self.ble.connect_to(slot, addr_type, addr)

        t0 = time.ticks_ms()
        while not self.ble.is_connected(slot):
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                self.ble.disconnect(slot)
                return None, None
            time.sleep_ms(50)

        # Handshake the LEGO device expects: InfoRequest, then start telemetry.
        self.ble.write(slot, bytes([0x00]))     # InfoRequest
        time.sleep_ms(50)
        dev.request_notifications(50)            # msg 40 -> periodic notifications
        self.devices[slot] = dev
        return slot, dev

    def is_connected(self, slot):
        return self.ble.is_connected(slot)

    def disconnect(self, slot):
        self.ble.disconnect(slot)
        self.devices.pop(slot, None)
