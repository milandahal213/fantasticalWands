# bledevice.py  –  ESP32C6 MicroPython BLE central driver
# Supports multiple simultaneous connections via named slots.

from micropython import const
import bluetooth
import micropython
from machine import Pin

micropython.alloc_emergency_exception_buf(256)

LED_PIN = 8
_led = Pin(LED_PIN, Pin.OUT) if LED_PIN is not None else None

def _led_set(state):
    if _led: _led.value(state)

SERVICE_UUID_16  = bluetooth.UUID(0xfd02)
SERVICE_UUID_128 = bluetooth.UUID('0000fd02-0000-1000-8000-00805f9b34fb')
WRITE_UUID       = bluetooth.UUID('0000fd02-0001-1000-8000-00805f9b34fb')
NOTIFY_UUID      = bluetooth.UUID('0000fd02-0002-1000-8000-00805f9b34fb')

_IRQ_SCAN_RESULT                 = const(5)
_IRQ_PERIPHERAL_CONNECT          = const(7)
_IRQ_PERIPHERAL_DISCONNECT       = const(8)
_IRQ_GATTC_SERVICE_RESULT        = const(9)
_IRQ_GATTC_SERVICE_DONE          = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE   = const(12)
_IRQ_GATTC_WRITE_DONE            = const(17)
_IRQ_GATTC_NOTIFY                = const(18)
_IRQ_MTU_EXCHANGE                = const(21)
_IRQ_CONNECTION_UPDATE           = const(27)
_IRQ_GET_SECRET                  = const(29)
_IRQ_SET_SECRET                  = const(30)

MTU_SIZE = 150

LEGO_COMPANY_ID = 0x0397  # LEGO company identifier in BLE manufacturer data


def _parse_lego_mfg(adv_data):
    """Parse BLE advertising data and return LEGO card info if present.
    Returns (product_id, card_color, card_serial) or (None, None, None)."""
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0 or i + length >= len(adv_data):
            break
        ad_type = adv_data[i + 1]
        if ad_type == 0xFF and length >= 8:
            # Manufacturer-specific: [len][0xFF][cid_lo][cid_hi][payload...]
            cid = adv_data[i + 2] | (adv_data[i + 3] << 8)
            if cid == LEGO_COMPANY_ID:
                payload = adv_data[i + 4 : i + 1 + length]
                # [product_group, product_device, card_color, serial_lo, serial_hi]
                if len(payload) >= 5:
                    product_id  = (payload[0] << 8) | payload[1]
                    card_color  = payload[2]
                    card_serial = payload[3] | (payload[4] << 8)
                    return product_id, card_color, card_serial
        i += length + 1
    return None, None, None


def _new_slot():
    return {
        'conn_handle':  None,
        'write_handle': None,
        'notify_handle':None,
        'start_handle': None,
        'end_handle':   None,
        'cccd_enabled': False,
        'mtu_done':     False,
        'callback':     None,
    }


class BLEDevice:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.config(mtu=MTU_SIZE)

        self._slots     = {}   # slot_name → slot state dict
        self._handle_map= {}   # conn_handle (int) → slot_name

        # current scan target
        self._scan_slot = None
        self._scan_name = None
        self._scan_mfg  = None
        self._scan_card_color  = None
        self._scan_card_serial = None
        self._scan_product_id  = None
        self._scan_seen = set()
        self._scan_found= False

        self.ble.irq(self._irq)
        _led_set(0)
        print("BLEDevice ready")

    # ── IRQ ──────────────────────────────────────────────────────────────────
    def _irq(self, event, data):

        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            if self._scan_found:
                return
            addr_str = ':'.join('%02X' % b for b in addr)
            if addr_str in self._scan_seen:
                return
            self._scan_seen.add(addr_str)

            name = self._decode(adv_data) or ''
            product_id, card_color, card_serial = _parse_lego_mfg(adv_data)

            # Decide whether this advertisement matches our filters
            match = False

            # Name filter
            if self._scan_name:
                if name and self._scan_name in name:
                    match = True
                else:
                    return  # name requested but doesn't match

            # Product ID filter (e.g. 513 = Double Motor)
            if self._scan_product_id is not None:
                if product_id != self._scan_product_id:
                    return
                match = True

            # Card filters (both required together)
            if self._scan_card_color is not None or self._scan_card_serial is not None:
                if card_color is None:
                    return  # not a LEGO device
                if (self._scan_card_color is not None and
                        card_color != self._scan_card_color):
                    return
                if (self._scan_card_serial is not None and
                        card_serial != self._scan_card_serial):
                    return
                match = True

            if not match:
                return

            self._scan_found = True
            print("Found '{}' color={} serial={:04d} for slot '{}'".format(
                name or '?',
                card_color if card_color is not None else '?',
                card_serial if card_serial is not None else 0,
                self._scan_slot))
            self.ble.gap_scan(None)
            self.ble.gap_connect(addr_type, addr)

        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, addr_type, addr = data
            slot_name = self._scan_slot
            self._scan_slot  = None
            self._scan_found = False
            self._slots[slot_name]['conn_handle'] = conn_handle
            self._handle_map[conn_handle] = slot_name
            _led_set(1)
            print("Connected → slot '{}'".format(slot_name))
            self.ble.gattc_discover_services(conn_handle)

        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            slot_name = self._handle_map.pop(conn_handle, None)
            if slot_name and slot_name in self._slots:
                s = self._slots[slot_name]
                s['conn_handle']  = None
                s['write_handle'] = None
                s['notify_handle']= None
                s['cccd_enabled'] = False
            if not self._handle_map:
                _led_set(0)
            print("Disconnected slot '{}'".format(slot_name))

        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_h, end_h, uuid = data
            if uuid == SERVICE_UUID_16 or uuid == SERVICE_UUID_128:
                slot_name = self._handle_map.get(conn_handle)
                if slot_name:
                    self._slots[slot_name]['start_handle'] = start_h
                    self._slots[slot_name]['end_handle']   = end_h

        elif event == _IRQ_GATTC_SERVICE_DONE:
            slot_name = self._handle_map.get(data[0])
            if slot_name:
                s = self._slots[slot_name]
                if s['start_handle'] and s['end_handle']:
                    self.ble.gattc_discover_characteristics(
                        data[0], s['start_handle'], s['end_handle'])
                else:
                    print("Service not found for slot '{}'".format(slot_name))

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_h, value_h, props, uuid = data
            slot_name = self._handle_map.get(conn_handle)
            if not slot_name: return
            s = self._slots[slot_name]
            if uuid == WRITE_UUID:
                s['write_handle']  = value_h
            elif uuid == NOTIFY_UUID:
                s['notify_handle'] = value_h

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            conn_handle = data[0]
            slot_name = self._handle_map.get(conn_handle)
            if slot_name:
                micropython.schedule(self._setup_notify,
                                     (conn_handle, slot_name))

        elif event == _IRQ_GATTC_NOTIFY:
            conn_handle, value_h, notify_data = data
            slot_name = self._handle_map.get(conn_handle)
            if not slot_name: return
            s = self._slots[slot_name]
            if value_h == s['notify_handle'] and s['callback']:
                s['callback'](notify_data)

        elif event == _IRQ_GATTC_WRITE_DONE:
            pass
        elif event == _IRQ_MTU_EXCHANGE:
            conn_handle, mtu = data
            slot_name = self._handle_map.get(conn_handle)
            if slot_name and slot_name in self._slots:
                self._slots[slot_name]['mtu_done'] = True
            print("MTU exchanged:", mtu)
        elif event == _IRQ_CONNECTION_UPDATE:
            pass
        elif event == _IRQ_GET_SECRET:
            return None
        elif event == _IRQ_SET_SECRET:
            return False
        else:
            print("Unhandled BLE event:", event)

    # ── deferred CCCD setup ───────────────────────────────────────────────────
    def _setup_notify(self, args):
        conn_handle, slot_name = args
        if slot_name not in self._slots: return
        s = self._slots[slot_name]
        if s['conn_handle'] is None or s['notify_handle'] is None: return
        try:
            self.ble.gattc_write(conn_handle, s['notify_handle'] + 1,
                                 bytes([1, 0]), 1)
            self.ble.gattc_exchange_mtu(conn_handle)
            s['cccd_enabled'] = True
            print("Slot '{}' ready".format(slot_name))
        except Exception as e:
            print("_setup_notify error:", e)

    # ── public API ────────────────────────────────────────────────────────────
    def scan(self, slot, name=None, duration=5000, manufacture=None,
             card_color=None, card_serial=None, product_id=None):
        """Scan and connect to a device, assigning it to the named slot.

        Filters (any combination):
            name         – substring match on BLE device name
            product_id   – 512=Single Motor, 513=Double Motor,
                           514=Color Sensor, 515=Controller
            card_color   – int 1..10 (LEGO Connection Card color)
            card_serial  – int 0..9999 (LEGO Connection Card serial number)
        """
        # Preserve callback if set_callback() was already called for this slot
        existing_cb = self._slots.get(slot, {}).get('callback')
        self._slots[slot] = _new_slot()
        self._slots[slot]['callback'] = existing_cb
        self._scan_slot        = slot
        self._scan_name        = name
        self._scan_mfg         = manufacture
        self._scan_card_color  = card_color
        self._scan_card_serial = card_serial
        self._scan_product_id  = product_id
        self._scan_found       = False
        self._scan_seen        = set()
        desc = name or ''
        if product_id  is not None: desc += ' product_id=' + str(product_id)
        if card_color  is not None: desc += ' color=' + str(card_color)
        if card_serial is not None: desc += ' serial={:04d}'.format(card_serial)
        print("Scanning for {} → slot '{}'...".format(desc.strip(), slot))
        self.ble.gap_scan(duration, 30000, 30000, True)

    def is_connected(self, slot):
        s = self._slots.get(slot, {})
        return (s.get('conn_handle')   is not None and
                s.get('notify_handle') is not None and
                s.get('write_handle')  is not None and
                s.get('cccd_enabled',  False) and
                s.get('mtu_done',      False))

    def write(self, slot, data):
        s = self._slots.get(slot, {})
        if s.get('conn_handle') is None or s.get('write_handle') is None:
            return
        try:
            if not isinstance(data, bytes):
                data = bytes(data)
            self.ble.gattc_write(s['conn_handle'], s['write_handle'], data)
        except Exception as e:
            print("Write error ({}): {}".format(slot, e))

    def set_callback(self, slot, cb):
        if slot not in self._slots:
            self._slots[slot] = _new_slot()
        self._slots[slot]['callback'] = cb

    def disconnect(self, slot):
        s = self._slots.get(slot, {})
        if s.get('conn_handle') is not None:
            self.ble.gap_disconnect(s['conn_handle'])

    def _decode(self, payload):
        i = 0
        while i < len(payload):
            if i + 2 > len(payload): break
            length = payload[i]
            if length == 0 or i + length + 1 > len(payload): break
            adv_type = payload[i + 1]
            if adv_type == 0xFF and length >= 3:
                mfg_id = payload[i + 3] << 8 | payload[i + 2]
                if   mfg_id == 0x004C: return "Apple"
                elif mfg_id == 0x0006: return "Microsoft"
                else: return "Mfg 0x{:04X}".format(mfg_id)
            if adv_type in (0x08, 0x09):
                try: return bytes(payload[i + 2 : i + length + 1]).decode('utf-8')
                except: return None
            i += length + 1
        return None