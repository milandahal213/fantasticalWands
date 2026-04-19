# bledevice.py  –  ESP32C6 MicroPython BLE central driver
# Compatible with LEGO SPIKE Prime / LEGO wireless protocol (service 0xFD02)

from micropython import const
import bluetooth
import micropython
from machine import Pin

micropython.alloc_emergency_exception_buf(256)

# ── built-in LED (active-high on most ESP32C6 devkits) ──────────────────────
LED_PIN = 8        # set to None to disable
_led    = Pin(LED_PIN, Pin.OUT) if LED_PIN is not None else None

def _led_set(state):
    if _led is not None:
        _led.value(state)

# ── LEGO service / characteristic UUIDs ─────────────────────────────────────
# The LEGO device advertises the full 128-bit form.  MicroPython on ESP32C6
# does NOT equate that to the short 16-bit UUID(0xfd02) in comparisons, so
# we keep both and accept either in the service-result handler.
SERVICE_UUID_16  = bluetooth.UUID(0xfd02)
SERVICE_UUID_128 = bluetooth.UUID('0000fd02-0000-1000-8000-00805f9b34fb')
WRITE_UUID       = bluetooth.UUID('0000fd02-0001-1000-8000-00805f9b34fb')
NOTIFY_UUID      = bluetooth.UUID('0000fd02-0002-1000-8000-00805f9b34fb')

_FLAG_WRITE  = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

# ── BLE IRQ event codes ──────────────────────────────────────────────────────
_IRQ_CENTRAL_CONNECT             = const(1)
_IRQ_CENTRAL_DISCONNECT          = const(2)
_IRQ_GATTS_WRITE                 = const(3)
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
# ── Extra events on ESP32C6 / newer MicroPython ──────────────────────────────
_IRQ_CONNECTION_UPDATE           = const(27)  # conn params updated – no action needed
_IRQ_GET_SECRET                  = const(29)  # pairing: MUST return None (no stored key)
_IRQ_SET_SECRET                  = const(30)  # pairing: return False to skip storing key

MTU_SIZE = 150


class BLEDevice:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.config(mtu=MTU_SIZE)

        self.conn_handle    = None
        self.write_handle   = None
        self.notify_handle  = None
        self.service_uuid_16  = SERVICE_UUID_16
        self.service_uuid_128 = SERVICE_UUID_128
        self.write_uuid       = WRITE_UUID
        self.notify_uuid      = NOTIFY_UUID
        self.callback         = None
        self._connecting      = False
        self.start_handle     = None
        self.end_handle       = None
        # Guard: do not signal "connected" until CCCD is enabled so the
        # main loop does not write before setup is complete.
        self._cccd_enabled    = False

        # scan state (populated by reset())
        self.mfg            = None
        self.name           = None
        self.seen_addresses = set()
        self.devices        = []
        self.found          = False

        self.ble.irq(self._irq)
        _led_set(0)
        print("BLEDevice ready  service:", self.service_uuid_128)

    # ── IRQ handler ─────────────────────────────────────────────────────────
    def _irq(self, event, data):

        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            addr_str     = ':'.join('%02X' % b for b in addr)
            name         = ''
            manufacturer = ''

            if adv_type == 4:
                name = self.decode(adv_data) or ''

            if addr_str not in self.seen_addresses:
                self.seen_addresses.add(addr_str)
                manufacturer = self.decode(adv_data) or ''
                name         = self.decode(adv_data) or ''
                self.devices.append({'device': addr_str,
                                     'manufacture': manufacturer,
                                     'name': name,
                                     'rssi': rssi})
                if (self.mfg and manufacturer == self.mfg) or \
                   (name and self.name and self.name in name):
                    print('Found:', name, manufacturer)
                    self.found = True
            else:
                for d in self.devices:
                    if d['device'] == addr_str:
                        if name and d['name'] != name:
                            d['name'] = name
                            if self.name and self.name in name:
                                print('Found (updated):', name)
                                self.found = True

            if self.found:
                self.ble.gap_scan(None)
                self._connecting = True
                self.ble.gap_connect(addr_type, addr)
                print("Connecting…")

        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, addr_type, addr = data
            self.conn_handle   = conn_handle
            self._connecting   = False
            self._cccd_enabled = False
            _led_set(1)
            self.ble.gattc_discover_services(self.conn_handle)
            print("Connected – discovering services…")

        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            self.conn_handle   = None
            self.write_handle  = None
            self.notify_handle = None
            self._cccd_enabled = False
            _led_set(0)
            print("Disconnected")

        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            print("Service found:", uuid)
            if uuid == self.service_uuid_16 or uuid == self.service_uuid_128:
                print("  -> LEGO service matched")
                self.start_handle = start_handle
                self.end_handle   = end_handle

        elif event == _IRQ_GATTC_SERVICE_DONE:
            if self.start_handle is not None and self.end_handle is not None:
                self.ble.gattc_discover_characteristics(
                    self.conn_handle, self.start_handle, self.end_handle)
            else:
                print("LEGO service not found – check device name / firmware")

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            # Record handles only – do NOT call gattc_write or
            # gattc_exchange_mtu here.  Calling BLE operations inside
            # CHARACTERISTIC_RESULT (before CHARACTERISTIC_DONE fires)
            # corrupts the BLE stack state on ESP32C6.  Setup is deferred
            # to _setup_notify(), scheduled from CHARACTERISTIC_DONE.
            conn_handle, def_handle, value_handle, properties, uuid = data
            print("Characteristic found:", uuid)
            if uuid == self.write_uuid:
                self.write_handle = value_handle
                print("  -> Write handle:", value_handle)
            elif uuid == self.notify_uuid:
                self.notify_handle = value_handle
                print("  -> Notify handle:", value_handle)

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            # All characteristics have been enumerated.  Now safe to enable
            # the CCCD and negotiate MTU.  Use micropython.schedule() so
            # the work runs in the main-thread context, not the IRQ context.
            print("Characteristic discovery done – scheduling notify setup…")
            if self.notify_handle is not None and self.conn_handle is not None:
                micropython.schedule(self._setup_notify, 0)

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if conn_handle == self.conn_handle and \
               value_handle == self.notify_handle and self.callback:
                self.callback(self.ble.gatts_read(value_handle))

        elif event == _IRQ_GATTC_NOTIFY:
            conn_handle, value_handle, notify_data = data
            if conn_handle == self.conn_handle and \
               value_handle == self.notify_handle and self.callback:
                self.callback(notify_data)

        elif event == _IRQ_GATTC_WRITE_DONE:
            # CCCD write acknowledged – no action needed.
            pass

        elif event == _IRQ_MTU_EXCHANGE:
            print("MTU exchanged – larger packets now supported")

        elif event == _IRQ_CONNECTION_UPDATE:
            # Peripheral updated connection parameters; stack applies them.
            pass

        elif event == _IRQ_GET_SECRET:
            # MUST return a value: None = no stored pairing key.
            return None

        elif event == _IRQ_SET_SECRET:
            # Decline storing bonding keys.
            return False

        else:
            print("Unhandled BLE event:", event)

    # ── deferred setup ───────────────────────────────────────────────────────
    def _setup_notify(self, _=None):
        """Enable CCCD and negotiate MTU. Runs via micropython.schedule()
        so it executes in the main-thread context, outside the IRQ."""
        if self.conn_handle is None or self.notify_handle is None:
            return
        try:
            # Write 0x0001 to the CCCD (descriptor handle = notify_handle + 1)
            # mode=1 requests a write-with-response so we get _GATTC_WRITE_DONE.
            self.ble.gattc_write(self.conn_handle,
                                 self.notify_handle + 1,
                                 bytes([1, 0]),
                                 1)
            self.ble.gattc_exchange_mtu(self.conn_handle)
            self._cccd_enabled = True
            print("CCCD enabled, MTU exchange requested – ready to use")
        except Exception as e:
            print("_setup_notify error:", e)

    # ── public API ───────────────────────────────────────────────────────────
    def write(self, data):
        """Send bytes to the LEGO device's write characteristic."""
        # IMPORTANT: use 'is None', not 'not x'.  conn_handle can be 0,
        # and 'not 0' is True – which would block every write on the first
        # connection.
        if self.conn_handle is None or self.write_handle is None:
            print("Not connected")
            return
        try:
            if not isinstance(data, bytes):
                data = bytes(data)
            self.ble.gattc_write(self.conn_handle, self.write_handle, data)
        except Exception as e:
            print("Write error:", e)

    def is_connected(self):
        """True only once handles are found AND CCCD setup is complete."""
        return (self.conn_handle   is not None and
                self.notify_handle is not None and
                self.write_handle  is not None and
                self._cccd_enabled)

    def set_callback(self, cb):
        self.callback = cb

    def disconnect(self):
        if self.conn_handle is not None:
            self.ble.gap_disconnect(self.conn_handle)
            self.conn_handle   = None
            self.write_handle  = None
            self.notify_handle = None
            self._cccd_enabled = False
            _led_set(0)

    def reset(self):
        self.ble.active(True)
        self.mfg            = None
        self.name           = None
        self.seen_addresses = set()
        self.devices        = []
        self.found          = False
        self.start_handle   = None
        self.end_handle     = None
        self._cccd_enabled  = False
        _led_set(0)

    def scan(self, duration=5000, manufacture=None, name=None):
        """Scan and auto-connect to the first matching device.

        duration    – scan window in ms (0 = scan forever)
        manufacture – manufacturer name substring to match
        name        – device name substring to match (e.g. 'Single Motor')
        """
        print("Scanning…  name='{}' mfg='{}'".format(name, manufacture))
        self.reset()
        self.mfg  = manufacture
        self.name = name
        self.ble.gap_scan(duration, 30000, 30000, True)

    def close(self):
        self.ble.gap_scan(None)
        self.ble.active(False)
        _led_set(0)

    # ── advertisement parser ─────────────────────────────────────────────────
    def decode(self, payload):
        """Extract device name or manufacturer string from an adv payload."""
        i = 0
        while i < len(payload):
            if i + 2 > len(payload):
                break
            length = payload[i]
            if length == 0 or i + length + 1 > len(payload):
                break
            adv_type = payload[i + 1]

            if adv_type == 0xFF and length >= 3:
                mfg_id = payload[i + 3] << 8 | payload[i + 2]
                if   mfg_id == 0x004C: return "Apple"
                elif mfg_id == 0x0006: return "Microsoft"
                else:                  return "Mfg 0x{:04X}".format(mfg_id)

            if adv_type in (0x08, 0x09):
                try:
                    return bytes(payload[i + 2 : i + length + 1]).decode('utf-8')
                except Exception:
                    return None

            i += length + 1
        return None