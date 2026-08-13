"""
ble.py — Web Bluetooth bridge for PyScript / Pyodide.

Wraps `navigator.bluetooth` so the rest of the app can talk to LEGO hardware
with plain Python. Browser-only (imports `js` / `pyodide.ffi`); it is never
imported under CPython.

Connection flow (must be triggered by a user gesture, e.g. a button click):
    handle = await connect(on_packet, on_disconnect)
    handle.send(frame_bytes)        # write a command
    await handle.disconnect()       # tear down

Web Bluetooth notes:
  * Secure context only — works on https:// and on http://localhost.
  * Chromium browsers only (Chrome / Edge); Firefox & Safari lack the API.
  * The browser shows its own device-chooser dialog; we filter to the LEGO
    service so only LEGO hardware appears.
"""

import asyncio

from js import navigator, Uint8Array, Object
from pyodide.ffi import create_proxy, to_js

import lego_ble as L

# Keep event-listener proxies alive (Pyodide GCs unreferenced proxies).
_live_proxies = []


def is_available():
    try:
        return bool(navigator.bluetooth)
    except Exception:
        return False


def _to_buffer(data: bytes):
    """Python bytes -> JS Uint8Array suitable for writeValue*."""
    return Uint8Array.new(to_js(list(data)))


def _dataview_to_bytes(value):
    """A characteristicvaluechanged DataView -> Python bytes."""
    arr = Uint8Array.new(value.buffer)
    return bytes(arr.to_py())


class _Handle:
    # Cap the outgoing queue so a BLE stall can't build unbounded latency;
    # under backpressure we drop the oldest frames and keep the newest, which
    # for the swing/mirror behaviors means the freshest motor target wins.
    _MAX_QUEUE = 16

    def __init__(self, device, server, write_char, notify_char, proxies):
        self.device = device
        self._server = server
        self._write = write_char
        self._notify = notify_char
        self._proxies = proxies
        self.name = device.name or "LEGO device"
        self._queue = []          # pending outgoing frames (bytes)
        self._draining = False

    def send(self, data: bytes):
        """Queue a command frame. Writes are drained one at a time.

        Web Bluetooth allows only one GATT operation in flight per device, so
        firing writes concurrently raises "GATT operation already in progress".
        We enqueue here and let a single drain task await each write in turn."""
        self._queue.append(data)
        if len(self._queue) > self._MAX_QUEUE:
            del self._queue[:-self._MAX_QUEUE]      # drop oldest under backpressure
        if not self._draining:
            self._draining = True
            asyncio.ensure_future(self._drain())

    async def _drain(self):
        try:
            while self._queue:
                data = self._queue.pop(0)
                try:
                    await self._write.writeValueWithoutResponse(_to_buffer(data))
                except Exception:
                    # Older Chromium spelled it writeValue; fall back.
                    try:
                        await self._write.writeValue(_to_buffer(data))
                    except Exception as e:
                        print("BLE write failed:", e)
        finally:
            self._draining = False

    async def disconnect(self):
        self._queue.clear()          # stop draining; don't write to a dead device
        try:
            if self._server and self._server.connected:
                self._server.disconnect()
        except Exception:
            pass
        for p in self._proxies:
            try:
                self._live_proxies_remove(p)
            except Exception:
                pass

    def _live_proxies_remove(self, p):
        if p in _live_proxies:
            _live_proxies.remove(p)
            p.destroy()


async def request_device():
    """Pop the browser device chooser, filtered to the LEGO GATT service."""
    options = to_js(
        {
            "filters": [{"services": [L.SERVICE_SHORT]}],
            "optionalServices": [L.SERVICE_SHORT, L.SERVICE_UUID],
        },
        dict_converter=Object.fromEntries,
    )
    return await navigator.bluetooth.requestDevice(options)


async def connect(on_packet, on_disconnect):
    """Show the chooser, connect GATT, subscribe to notifications.

    on_packet(bytes)     called for every incoming GATT notification
    on_disconnect()      called when the device drops
    Returns a _Handle, or raises on failure / user cancel.
    """
    device = await request_device()

    proxies = []

    def _on_value_changed(event):
        try:
            on_packet(_dataview_to_bytes(event.target.value))
        except Exception as e:
            print("notification handler error:", e)

    def _on_gatt_disconnected(event):
        try:
            on_disconnect()
        except Exception as e:
            print("disconnect handler error:", e)

    server = await device.gatt.connect()
    service = await server.getPrimaryService(L.SERVICE_SHORT)
    write_char = await service.getCharacteristic(L.WRITE_UUID)
    notify_char = await service.getCharacteristic(L.NOTIFY_UUID)

    value_proxy = create_proxy(_on_value_changed)
    disc_proxy = create_proxy(_on_gatt_disconnected)
    _live_proxies.extend([value_proxy, disc_proxy])
    proxies.extend([value_proxy, disc_proxy])

    notify_char.addEventListener("characteristicvaluechanged", value_proxy)
    await notify_char.startNotifications()
    device.addEventListener("gattserverdisconnected", disc_proxy)

    return _Handle(device, server, write_char, notify_char, proxies)
