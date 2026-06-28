"""
DeviceManager — auto-detect and connect to any LEGO Education hardware.

Usage:
    from device_manager import DeviceManager
    dm = DeviceManager()
    results = dm.scan(card_serial=2279, card_color='white')
    dm.connect_results(results)
    dm.print_telemetry()
    dm.disconnect_all()
"""

import threading
import legoeducation as le
from lelib import singleMotor, doubleMotor, colorSensor, controller

SCAN_TIMEOUT = 2  # seconds

DEVICE_TYPES = [singleMotor, doubleMotor, colorSensor, controller]

DEVICE_LABELS = {
    singleMotor: 'Single Motor',
    doubleMotor: 'Double Motor',
    colorSensor: 'Color Sensor',
    controller:  'Controller',
}

COLOR_MAP = {
    'red':     le.LEGO_COLOR_RED,
    'yellow':  le.LEGO_COLOR_YELLOW,
    'blue':    le.LEGO_COLOR_BLUE,
    'teal':    le.LEGO_COLOR_TEAL,
    'green':   le.LEGO_COLOR_GREEN,
    'purple':  le.LEGO_COLOR_PURPLE,
    'white':   le.LEGO_COLOR_WHITE,
    'magenta': le.LEGO_COLOR_MAGENTA,
    'orange':  le.LEGO_COLOR_ORANGE,
    'azure':   le.LEGO_COLOR_AZURE,
}

# Hex colours for UI rendering
COLOR_HEX = {
    'red':     '#de1a21',
    'yellow':  '#ffd400',
    'blue':    '#006cb8',
    'teal':    '#1de9b6',
    'green':   '#61a836',
    'purple':  '#4b2f91',
    'white':   '#f5f5f5',
    'magenta': '#e4599e',
    'orange':  '#f57d20',
    'azure':   '#78bfea',
    None:      '#607d8b',   # unknown / no filter
}


class ScanResult:
    """A device found during a scan, not yet connected."""

    def __init__(self, cls, dev, ble_result, card_color_name):
        self.cls             = cls
        self.dev             = dev          # lelib device instance (reused for connect)
        self.ble_result      = ble_result   # Bleak BLEDevice
        self.device_type     = DEVICE_LABELS[cls]
        self.mac             = getattr(ble_result, 'address', '??:??:??:??:??:??')

        # Parse color, serial, and emoji from the device name
        ble_color, ble_serial, ble_emoji = _parse_device_name(ble_result)
        self.card_color_name = ble_color if ble_color is not None else card_color_name
        self.color_hex       = COLOR_HEX.get(self.card_color_name, COLOR_HEX[None])
        self.card_serial     = ble_serial
        self.emoji           = ble_emoji

    def __repr__(self):
        return (f"ScanResult({self.device_type}, serial={self.card_serial}, "
                f"color={self.card_color_name}, mac={self.mac})")


import re

# Emoji in device name → color name
_EMOJI_TO_COLOR = {
    '🟥': 'red',
    '🟨': 'yellow',
    '🟦': 'blue',
    '🩵': 'teal',
    '🟩': 'green',
    '🟪': 'purple',
    '⬜': 'white',
    '⬜️': 'white',
    '🩷': 'magenta',
    '🟧': 'orange',
    '🔵': 'azure',
}


def _parse_device_name(ble_result):
    """Parse color name, serial, and emoji from the LEGO device BLE name.

    Name format: '{emoji} {serial} {device_type}'
              or '{emoji}    {device_type}'  (no serial when card not paired)
    Returns (color_name, serial, emoji) — any may be None if not found.
    """
    name = getattr(ble_result, 'name', '') or ''

    # Extract first emoji character
    emoji = None
    color_name = None
    for em, col in _EMOJI_TO_COLOR.items():
        if name.startswith(em):
            emoji = em
            color_name = col
            break

    # Extract serial: first run of digits in the name
    serial = None
    m = re.search(r'\d+', name)
    if m:
        serial = int(m.group())

    return color_name, serial, emoji


def _extract_serial(ble_result) -> int | None:
    _, serial, _ = _parse_device_name(ble_result)
    return serial


def _extract_color_name(ble_result) -> str | None:
    color_name, _, _ = _parse_device_name(ble_result)
    return color_name


def _extract_emoji(ble_result) -> str | None:
    _, _, emoji = _parse_device_name(ble_result)
    return emoji


class DeviceManager:
    """Manages multiple simultaneous LEGO Education BLE connections."""

    def __init__(self):
        self.devices = {}   # label -> device instance

    # ── Scanning ─────────────────────────────────────────────────────────────

    def scan(self, card_serial: int | None = None,
             card_color: str | None = None,
             on_found=None) -> list:
        """Scan for SCAN_TIMEOUT seconds across all device types in parallel.

        Returns a list of ScanResult objects (not yet connected).
        on_found(result): optional callback invoked as each device is discovered.
        card_serial=None or 0  →  no serial filter.
        card_color=None        →  no colour filter.
        """
        serial   = card_serial if card_serial else None
        color_id = None
        color_name = card_color.lower() if card_color else None

        if color_name:
            color_id = COLOR_MAP.get(color_name)
            if color_id is None:
                raise ValueError(
                    f"Unknown color '{card_color}'. "
                    f"Valid colors: {', '.join(COLOR_MAP)}"
                )

        all_found = []
        found_lock = threading.Lock()

        def try_type(cls):
            try:
                dev = cls()
                results = dev.search(
                    timeout=SCAN_TIMEOUT,
                    card_color=color_id,
                    card_serial=serial,
                )
                if results:
                    with found_lock:
                        for ble_result in results:
                            sr = ScanResult(cls, dev, ble_result, color_name)
                            all_found.append(sr)
                            if on_found:
                                on_found(sr)
                            dev = cls()   # fresh instance for next result
            except Exception:
                pass

        threads = [threading.Thread(target=try_type, args=(cls,), daemon=True)
                   for cls in DEVICE_TYPES]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return all_found

    # ── Connecting ────────────────────────────────────────────────────────────

    def connect_results(self, results: list) -> list:
        """Connect a list of ScanResult objects and register them."""
        connected = []
        for sr in results:
            label = self._unique_label(sr.device_type)
            sr.dev.connect(device=sr.ble_result)
            sr.dev.device_notification_request(100)
            self.devices[label] = sr.dev
            connected.append((label, sr.dev))
        return connected

    def scan_and_connect(self, card_serial: int | None = None,
                         card_color: str | None = None) -> list:
        """Convenience: scan then connect everything found."""
        results = self.scan(card_serial=card_serial, card_color=card_color)
        if not results:
            raise RuntimeError(
                "No LEGO devices found"
                + (f" with serial={card_serial}" if card_serial else "")
                + (f" color={card_color}" if card_color else "")
            )
        return self.connect_results(results)

    # ── Disconnection ─────────────────────────────────────────────────────────

    def disconnect(self, label: str):
        dev = self.devices.pop(label, None)
        if dev:
            dev.disconnect()

    def disconnect_all(self):
        for dev in list(self.devices.values()):
            dev.disconnect()
        self.devices.clear()

    # ── Telemetry ─────────────────────────────────────────────────────────────

    def read_all(self) -> dict:
        snapshot = {}
        for label, dev in self.devices.items():
            snapshot[label] = _read_device(dev)
        return snapshot

    def print_telemetry(self):
        for label, values in self.read_all().items():
            parts = '  '.join(f"{k}={v}" for k, v in values.items())
            print(f"[{label}]  {parts}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _unique_label(self, base: str) -> str:
        if base not in self.devices:
            return base
        i = 2
        while f"{base} {i}" in self.devices:
            i += 1
        return f"{base} {i}"

    def __repr__(self):
        return f"DeviceManager({list(self.devices)})"


def _read_device(dev) -> dict:
    """Extract the relevant sensor values from any device type."""
    if isinstance(dev, doubleMotor):
        return {
            'pos_L':   dev.motor[0].position,
            'pos_R':   dev.motor[1].position,
            'speed_L': dev.motor[0].speed,
            'speed_R': dev.motor[1].speed,
            'yaw':     dev.imu_device.yaw,
        }
    if isinstance(dev, singleMotor):
        return {
            'position': dev.motor.position,
            'speed':    dev.motor.speed,
        }
    if isinstance(dev, controller):
        return {
            'left':  dev.sensor.leftPercent,
            'right': dev.sensor.rightPercent,
        }
    if isinstance(dev, colorSensor):
        color_names = {
            0: 'none',  1: 'red',    2: 'yellow', 3: 'blue',
            4: 'teal',  5: 'green',  6: 'purple',  7: 'white',
            8: 'magenta', 9: 'orange', 10: 'azure',
        }
        return {
            'color':      color_names.get(dev.sensor.color, '?'),
            'reflection': dev.sensor.reflection,
        }
    return {}
