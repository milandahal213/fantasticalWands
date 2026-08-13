# bledevice.py  –  ESP32C6 MicroPython BLE central driver
# Supports multiple simultaneous connections via named slots.

from micropython import const
import bluetooth
import micropython
import time
from machine import Pin

micropython.alloc_emergency_exception_buf(256)

LED_PIN = 8
_led = Pin(LED_PIN, Pin.OUT) if LED_PIN is not None else None

def _led_set(state):
    if _led: _led.value(state)

SERVICE_UUID_16_RAW = 0xFD02
SERVICE_UUID_16  = bluetooth.UUID(0xfd02)
SERVICE_UUID_128 = bluetooth.UUID('0000fd02-0000-1000-8000-00805f9b34fb')
WRITE_UUID       = bluetooth.UUID('0000fd02-0001-1000-8000-00805f9b34fb')
NOTIFY_UUID      = bluetooth.UUID('0000fd02-0002-1000-8000-00805f9b34fb')

_IRQ_SCAN_RESULT                 = const(5)
_IRQ_SCAN_DONE                   = const(6)
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
    Returns (product_id, card_color, card_serial) or (None, None, None).

    The color byte is run through program_cards.remap_color() so it
    matches the value read off NFC cards by read_card_universal().
    This is the SAME remap used everywhere — one source of truth."""
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
                    # Lazy import — bledevice.py loads before program_cards
                    # on some boot paths, and we don't want a hard dep.
                    try:
                        from program_cards import remap_color
                        card_color = remap_color(payload[2])
                    except ImportError:
                        card_color = payload[2]
                    card_serial = payload[3] | (payload[4] << 8)
                    return product_id, card_color, card_serial
        i += length + 1
    return None, None, None


def _valid_stick_nibble(b):
    """True if the broadcast byte's low nibble is a real stick reading
    (0..3 = stop..+3, 0xD..0xF = -3..-1). 0x4..0xC is the protocol's own
    'dead / out of range' band and should never come from a working stick —
    seeing it means a corrupted or spurious packet, not a real position."""
    n = b & 0x0F
    return n <= 3 or n >= 0x0D


def _parse_fd02_service(adv_data):
    """Return the FD02 service-data payload (bytes after the 16-bit UUID) or None.

    LEGO color sensors / controllers broadcast their live state here (see the
    SimpleLE card_mode notes):
        [0] device type (0x02 color sensor, 0x03 controller)
        [1] card colour (firmware code)   [2] token   [3-4] serial (LE)
        [5] color sensor: detected colour (firmware code, 0xff = none)
        [5-6] controller: left / right stick axes
    """
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0 or i + length + 1 > len(adv_data):
            break
        # 0x16 = Service Data - 16-bit UUID
        if adv_data[i + 1] == 0x16 and length >= 3:
            uuid = adv_data[i + 2] | (adv_data[i + 3] << 8)
            if uuid == SERVICE_UUID_16_RAW:
                return bytes(adv_data[i + 4 : i + length + 1])
        i += length + 1
    return None


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
        # Switch to external antenna before activating BLE.
        # GPIO3 = antenna select A (low = external path enabled)
        # GPIO14 = antenna select B (high = external antenna)
        # Must be done before ble.active(True) or the radio starts on PCB antenna.
        Pin(3,  Pin.OUT).value(0)
        time.sleep_ms(100)
        Pin(14, Pin.OUT).value(1)

        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.config(mtu=MTU_SIZE)

        self._slots     = {}   # slot_name → slot state dict
        self._handle_map= {}   # conn_handle (int) → slot_name

        # current scan target (single-target mode used by scan())
        self._scan_slot = None
        self._scan_name = None
        self._scan_mfg  = None
        self._scan_card_color  = None
        self._scan_card_serial = None
        self._scan_product_id  = None
        self._scan_seen = set()
        self._scan_found= False

        # discover mode (collects multiple matches, no auto-connect)
        self._discover_active     = False
        self._discover_results    = []   # list of result dicts
        self._discover_seen_addrs = set()
        self._discover_filter     = None # callable(name, pid, color, serial) -> bool
        self._discover_done       = False

        # sensor-listen mode: passively read FD02 broadcasts (color sensor /
        # controller live state) while (optionally) also advertising. Keyed by
        # device type byte (0x02 = color sensor, 0x03 = controller).
        self._sensor_active = False
        self._sensor_serial = None       # only keep broadcasts from this card serial
        self._sensor_color  = None       # ...AND this card colour (firmware byte)
        self._sensor_state  = {}         # 0x02 -> {...}, 0x03 -> {...}

        self.ble.irq(self._irq)
        self._disconnect_callback = None   # optional: called with slot_name on disconnect
        _led_set(0)
        print("BLEDevice ready")

    # ── IRQ ──────────────────────────────────────────────────────────────────
    def _irq(self, event, data):

        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            addr_str = ':'.join('%02X' % b for b in addr)

            # ── Sensor-listen mode: passively decode FD02 live state ──────
            if self._sensor_active:
                payload = _parse_fd02_service(adv_data)
                if payload is not None and len(payload) >= 7:
                    dtype  = payload[0]
                    color  = payload[1]
                    serial = payload[3] | (payload[4] << 8)
                    # Only devices wearing the EXACT tapped card (colour AND
                    # serial) — a serial alone is ambiguous across colours.
                    if ((self._sensor_serial is None or serial == self._sensor_serial)
                            and (self._sensor_color is None or color == self._sensor_color)):
                        if dtype == 0x02:      # color sensor: byte5 = detected colour
                            self._sensor_state[0x02] = {
                                'color': payload[5], 't': time.ticks_ms()}
                        elif dtype == 0x03:    # controller: byte6=LEFT, byte5=RIGHT
                            # A dead/out-of-range nibble (see _valid_stick_nibble)
                            # means a corrupted or spurious packet, not a real
                            # stick position — hold the last valid reading for
                            # that axis instead of snapping the display to
                            # "stop" on every glitch.
                            prev = self._sensor_state.get(0x03, {})
                            left_raw, right_raw = payload[6], payload[5]
                            self._sensor_state[0x03] = {
                                'left':  left_raw  if _valid_stick_nibble(left_raw)
                                         else prev.get('left', 0),
                                'right': right_raw if _valid_stick_nibble(right_raw)
                                         else prev.get('right', 0),
                                't': time.ticks_ms()}
                # fall through — a device could also be relevant to discover(),
                # but in practice sensor-listen runs on its own.
                return

            # ── Discover mode: collect everything that matches, don't connect
            if self._discover_active:
                if addr_str in self._discover_seen_addrs:
                    return
                name = self._decode(adv_data) or ''
                product_id, card_color, card_serial = _parse_lego_mfg(adv_data)
                # Only LEGO devices are interesting here
                if product_id is None:
                    return
                # Debug: log every LEGO device we see and whether it matched
                matched = (self._discover_filter is None or
                           self._discover_filter(name, product_id,
                                                 card_color, card_serial))
                print("  adv: pid={} color={} serial={} match={}".format(
                    product_id, card_color, card_serial,
                    'yes' if matched else 'no'))
                if not matched:
                    return
                self._discover_seen_addrs.add(addr_str)
                self._discover_results.append({
                    'addr_type':   addr_type,
                    'addr':        bytes(addr),
                    'name':        name,
                    'product_id':  product_id,
                    'card_color':  card_color,
                    'card_serial': card_serial,
                    'rssi':        rssi,
                })
                return

            # ── Single-target scan mode (existing behaviour)
            if self._scan_found:
                return
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

        elif event == _IRQ_SCAN_DONE:
            if self._discover_active:
                self._discover_done = True

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
            if self._disconnect_callback and slot_name:
                try: micropython.schedule(self._disconnect_callback, slot_name)
                except: pass

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

    def discover(self, duration_ms=5000, card_color=None, card_serial=None,
                 product_id=None, name=None, filter_fn=None,
                 progress_cb=None, idle_cb=None):
        """Scan for ``duration_ms`` and return ALL matching LEGO devices.

        Does NOT connect. Use this when you want to know what's around
        (e.g. "every device wearing card color X serial Y") and connect
        to each one yourself afterwards.

        Filters work like ``scan()``. ``filter_fn(name, product_id,
        card_color, card_serial)`` is an optional extra predicate.

        ``progress_cb(result_dict)`` is called once per *new* device found
        during the scan — handy for blinking a status LED as devices arrive.

        Returns a list of dicts:
            [{'addr_type', 'addr', 'name', 'product_id',
              'card_color', 'card_serial', 'rssi'}, ...]
        """
        def _filter(n, pid, col, ser):
            if name and (not n or name not in n):           return False
            if product_id  is not None and pid != product_id:   return False
            if card_color  is not None and col != card_color:   return False
            if card_serial is not None and ser != card_serial:  return False
            if filter_fn is not None and not filter_fn(n, pid, col, ser):
                return False
            return True

        self._discover_active     = True
        self._discover_results    = []
        self._discover_seen_addrs = set()
        self._discover_filter     = _filter
        self._discover_done       = False

        # interval/window in microseconds — same as scan() for parity
        self.ble.gap_scan(duration_ms, 30000, 30000, True)

        # Wait for the scan to finish, reporting new finds as they arrive
        last_seen = 0
        start = time.ticks_ms()
        while not self._discover_done:
            # Surface any newly arrived results to the progress callback
            if progress_cb is not None:
                while last_seen < len(self._discover_results):
                    try:
                        progress_cb(self._discover_results[last_seen])
                    except Exception as e:
                        print("progress_cb err:", e)
                    last_seen += 1
            # Safety net: gap_scan should fire _IRQ_SCAN_DONE on its own,
            # but if it ever doesn't, bail at duration + 1s.
            if time.ticks_diff(time.ticks_ms(), start) > duration_ms + 1000:
                try: self.ble.gap_scan(None)
                except: pass
                break
            if idle_cb is not None:
                try: idle_cb()
                except Exception as e: print("idle_cb err:", e)
            time.sleep_ms(50)

        # Drain any results that arrived between the last poll and SCAN_DONE
        if progress_cb is not None:
            while last_seen < len(self._discover_results):
                try:
                    progress_cb(self._discover_results[last_seen])
                except Exception as e:
                    print("progress_cb err:", e)
                last_seen += 1

        results = self._discover_results
        self._discover_active  = False
        self._discover_filter  = None
        self._discover_results = []
        return results

    def connect_to(self, slot, addr_type, addr):
        """Connect to a previously-discovered device by raw BLE address.
        Use the addr_type/addr returned by discover().
        """
        existing_cb = self._slots.get(slot, {}).get('callback')
        self._slots[slot] = _new_slot()
        self._slots[slot]['callback'] = existing_cb
        self._scan_slot  = slot
        self._scan_found = False
        # gap_connect kicks off the same chain as the post-scan path
        self.ble.gap_connect(addr_type, addr)

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

    def set_disconnect_callback(self, cb):
        """Register a callback invoked (via micropython.schedule) when any
        slot disconnects. Signature: cb(slot_name: str)."""
        self._disconnect_callback = cb

    def set_callback(self, slot, cb):
        if slot not in self._slots:
            self._slots[slot] = _new_slot()
        self._slots[slot]['callback'] = cb

    def disconnect(self, slot):
        s = self._slots.get(slot, {})
        if s.get('conn_handle') is not None:
            self.ble.gap_disconnect(s['conn_handle'])

    # ── sensor listen (passive FD02 broadcast reader) ─────────────────────────
    def sensor_listen(self, card_serial=None, card_color=None):
        """Start a continuous passive scan that decodes FD02 live state from
        LEGO color sensors / controllers. Poll sensor_snapshot() for the latest.

        card_serial / card_color – if given, ignore broadcasts from any other
            card. Both are matched together (the (colour, serial) pair is the
            real key — serials repeat across colours). card_color is the raw
            firmware colour byte (== the card's stored colour byte).

        NOTE: this runs gap_scan continuously. Advertising a drive beacon at the
        same time relies on the radio doing concurrent advertise+scan; if a
        board can't, switch the drive loop to time-slice (advertise, stop, scan)."""
        self._sensor_serial = card_serial
        self._sensor_color  = card_color
        self._sensor_state  = {}
        self._sensor_active = True
        # duration 0 = scan until stopped; active scan to catch scan-response too
        self.ble.gap_scan(0, 30000, 30000, True)

    def sensor_stop(self):
        self._sensor_active = False
        try:
            self.ble.gap_scan(None)
        except Exception:
            pass

    def sensor_snapshot(self):
        """Return a shallow copy of the latest decoded sensor state:
            {0x02: {'color': <firmware code>, 't': ms},
             0x03: {'left': b, 'right': b, 't': ms}}   (absent keys = not seen)."""
        return dict(self._sensor_state)

    # ── advertising (broadcaster role) ────────────────────────────────────────
    def advertise(self, payload, interval_us=100_000):
        """Broadcast a raw (non-connectable) advertising payload on the shared
        BLE radio. Call again with new bytes to update it. Used by advertise
        mode to send an fd02 LEGO beacon — never runs while scanning/connecting."""
        try:
            self.ble.gap_advertise(None)
        except Exception:
            pass
        try:
            self.ble.gap_advertise(interval_us, adv_data=payload, connectable=False)
        except Exception as e:
            print("advertise error:", e)

    def advertise_stop(self):
        try:
            self.ble.gap_advertise(None)
        except Exception:
            pass

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