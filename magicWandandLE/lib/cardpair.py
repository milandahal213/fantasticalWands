# cardpair.py — tap a LEGO Connection Card on the wand to discover and
# connect to every LEGO device wearing that same card.
#
# Card-lock model: the first tap binds the wand to that card for the
# rest of the session. Subsequent taps with the same card re-scan and
# add any new devices (existing connections stay). Taps with a
# different card are rejected with a short buzz/beep.
#
# All LED display is handled by WandUI:
#   - Row 0:    device count (solid pixels = connected, never animated)
#   - Rows 1-3: transient animations (spinner, flash, etc.)
#   - Row 4:    bound card color indicator (always-on once bound)
# Connections are hard-capped at MAX_DEVICES (5).
#
# Usage:
#   from wand import Wand
#   from bledevice import BLEDevice
#   from cardpair import run_card_loop
#
#   w   = Wand()
#   ble = BLEDevice()
#   run_card_loop(w, ble)
#   # Connections live on w.connections, bound card on w.bound_card.

import time

from newhub import (Hub,
    SINGLE_MOTOR, DOUBLE_MOTOR, COLOR_SENSOR, CONTROLLER)
from wand_ui import WandUI, MAX_DEVICES


# product_id → (slot prefix, human label)
_DEVICE_INFO = {
    SINGLE_MOTOR: ('smotor', 'Single Motor'),
    DOUBLE_MOTOR: ('dmotor', 'Double Motor'),
    COLOR_SENSOR: ('color',  'Color Sensor'),
    CONTROLLER:   ('ctrl',   'Controller'),
}


class CardPairError(Exception):
    pass


def _get_or_make_ui(wand):
    """Return the WandUI for this wand, creating one if needed.
    Persisted on the wand so that subsequent card-loop iterations
    reuse the same top-row state (number of connected devices)."""
    ui = getattr(wand, 'ui', None)
    if ui is None:
        ui = WandUI(wand)
        wand.ui = ui
    return ui


def _connect_one(wand, ui, ble, result, slot_name, label, on_data,
                 spin_until_connect=True):
    """Attempt to connect to one discovered device. Updates the LED state
    via WandUI (mark_finding → mark_connected / mark_failed) and arms the
    hub callback. Returns the Hub on success or None on failure.

    If ``spin_until_connect`` is True, the spinner keeps animating while
    we wait for the GATT handshake to finish, so the wand stays alive."""
    slot_idx = ui.mark_finding()
    if slot_idx is None:
        return None     # at MAX_DEVICES cap

    h = Hub(ble_device=ble, slot=slot_name)
    h.data = {}

    def _make_cb(hub, sname):
        def _cb(raw):
            try:
                parsed = hub.parse([b for b in raw])
                if isinstance(parsed, dict):
                    hub.data.update(parsed)
                    if on_data is not None:
                        try: on_data(sname, parsed)
                        except Exception as e: print("on_data err:", e)
            except Exception as e:
                print("parse err ({}):".format(sname), e)
        return _cb
    h.set_callback(_make_cb(h, slot_name))

    try:
        ble.connect_to(slot_name, result['addr_type'], result['addr'])
    except Exception as e:
        print("  connect_to error:", e)
        ui.mark_failed(slot_idx)
        return None

    # Wait for GATT setup, keep the spinner moving so it doesn't freeze
    deadline = time.ticks_ms() + 6000
    last_tick = 0
    while not ble.is_connected(slot_name):
        if time.ticks_diff(time.ticks_ms(), deadline) > 0:
            break
        if spin_until_connect:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_tick) >= ui.SPINNER_STEP_MS:
                ui.tick_spinner()
                last_tick = now
        time.sleep_ms(20)

    if not ble.is_connected(slot_name):
        print("  ✗ {} timed out".format(label))
        ui.mark_failed(slot_idx)
        try: ble.disconnect(slot_name)
        except: pass
        return None

    h.write([0x00])
    h.feed(updateTime=200)
    ui.mark_connected(slot_idx, product_id=result.get('product_id'), slot_name=slot_name)

    return h


def _seed_slot_counts(existing, slot_prefix):
    """Walk existing connections to build {base_slot: highest_index_used}
    so new slot names don't collide."""
    counts = {}
    if not existing: return counts
    bases = {b for b, _ in _DEVICE_INFO.values()}
    for slot_name, _, _ in existing:
        s = slot_name[len(slot_prefix):] if slot_prefix and \
            slot_name.startswith(slot_prefix) else slot_name
        j = len(s)
        while j > 0 and s[j-1].isdigit():
            j -= 1
        base = s[:j]
        idx_part = s[j:]
        n = int(idx_part) if idx_part else 1
        if base in bases:
            counts[base] = max(counts.get(base, 0), n)
    return counts


def _pick_slot_name(pid, slot_counts, slot_prefix):
    """Allocate a unique slot name like 'smotor', 'smotor2', etc."""
    info = _DEVICE_INFO.get(pid)
    if info is None: return None, None
    base_slot, label = info
    n = slot_counts.get(base_slot, 0) + 1
    slot_counts[base_slot] = n
    slot_name = (slot_prefix + base_slot) if n == 1 \
                else (slot_prefix + base_slot + str(n))
    return slot_name, label


# ─── Scan-and-connect on a card tap ──────────────────────────────────────────

def _scan_and_connect(wand, ble, card_color, card_serial,
                      existing=None, scan_ms=1500, slot_prefix='',
                      on_data=None):
    """Run one scan-and-connect pass for devices wearing the given card.

    Animates: spinner during scan, blink/solid on top row per device,
    quick flash on completion. Buzzes the vibration motor briefly as
    each new device completes its connection.

    Args:
        wand          – Wand instance (must have ``ui`` attribute set).
        ble           – shared BLEDevice.
        card_color    – LEGO color id (0..10) we're scanning for.
        card_serial   – LEGO serial number (0..9999) we're scanning for.
        existing      – list of currently-connected (slot, hub, info)
                        tuples; their addresses are excluded from the scan.
        scan_ms       – discover window. ~1500 ms is usually enough.
        slot_prefix   – string prepended to every assigned slot name.
        on_data       – optional callback fn(slot_name, parsed_dict).

    Returns the list of newly connected (slot, hub, info) tuples.
    May return an empty list. Does NOT raise on 'nothing new'; only
    raises CardPairError on hard misconfiguration.
    """
    ui = wand.ui

    # Register disconnect callback so LEDs update when a device drops
    def _on_disconnect(slot_name):
        try: ui.mark_disconnected(slot_name)
        except Exception as e: print("disconnect ui err:", e)
    ble.set_disconnect_callback(_on_disconnect)

    # Compute how many top-row slots are still free
    free_slots = MAX_DEVICES - ui.device_count()
    if free_slots <= 0:
        # Already at cap; brief acknowledgment, no work
        wand.beep(800, 80)
        ui.vibrate(30)
        return []

    # Audible "starting to scan" cue — every tap-programming scan (initial
    # connect or a re-tap looking for more devices) gets this before the
    # actual BLE discover starts.
    try:
        wand.play_scan_jingle()
    except Exception:
        pass

    # ── Discover ─────────────────────────────────────────────────
    state = {'last_tick': 0, 'newly_finding': 0}

    def _animate():
        now = time.ticks_ms()
        if time.ticks_diff(now, state['last_tick']) >= ui.SPINNER_STEP_MS:
            ui.tick_spinner()
            state['last_tick'] = now

    existing_addrs = set()
    if existing:
        for _, _, info in existing:
            if info and 'addr' in info:
                existing_addrs.add(bytes(info['addr']))

    def _on_found(r):
        if r.get('product_id') not in _DEVICE_INFO:
            return
        if bytes(r['addr']) in existing_addrs:
            return    # already connected
        if state['newly_finding'] >= free_slots:
            return    # would exceed cap
        ui.mark_finding()
        state['newly_finding'] += 1
        wand.beep(2000, 30)

    results = ble.discover(duration_ms=scan_ms,
                           card_color=card_color, card_serial=card_serial,
                           progress_cb=_on_found, idle_cb=_animate)

    # Strip already-connected, over-cap, and unknown product ids
    candidates = []
    for r in results:
        if r.get('product_id') not in _DEVICE_INFO:
            continue
        if bytes(r['addr']) in existing_addrs:
            continue
        candidates.append(r)
        if len(candidates) >= free_slots:
            break

    # Reset transient finding flags; each _connect_one re-marks one
    ui.finding = [False] * MAX_DEVICES

    if not candidates:
        # Nothing new — short low buzz/beep, no flash
        wand.beep(800, 80)
        ui.vibrate(30)
        ui.clear_animation()
        return []

    # ── Connect each candidate sequentially ──────────────────────
    slot_counts = _seed_slot_counts(existing, slot_prefix)
    connected = []
    for r in candidates:
        pid = r['product_id']
        slot_name, label = _pick_slot_name(pid, slot_counts, slot_prefix)
        if slot_name is None:
            continue
        hub = _connect_one(wand, ui, ble, r, slot_name, label, on_data)
        if hub is not None:
            connected.append((slot_name, hub, r))
            wand.beep(1800, 50)
            ui.vibrate(40)            # per-device confirmation buzz

    if not connected:
        wand.beep(300, 250)
        ui.clear_animation()
        return []

    ui.flash_anim(flashes=2)
    ui.clear_animation()
    return connected


def run_card_loop(wand, ble, scan_ms=700, slot_prefix='', on_data=None,
                  poll_ms=100):
    """Sit forever waiting for card taps. Each accepted tap triggers a
    scan-and-connect pass.

    Card-lock rules:
      * First tap: binds the wand to that card. Scan immediately.
      * Subsequent tap with the SAME card: scan again, add any new
        devices. Already-connected devices stay.
      * Tap with a DIFFERENT card while bound: short "wrong card" buzz
        and beep; no scan, no disconnect, no card-row change.

    The function never returns under normal use. Catch KeyboardInterrupt
    in the caller to shut down cleanly.

    Returns a list of all currently-connected (slot, hub, info) tuples
    at any point you peek at the wand. The list is also stored on
    ``wand.connections`` so callers (programming-system event handlers,
    UI loops) can find it.
    """

    # Make sure the wand has a UI and a connections list
    ui = _get_or_make_ui(wand)
    wand.connections = getattr(wand, 'connections', [])
    wand.bound_card  = getattr(wand, 'bound_card',  None)

    # NeoPixel starts blank, then a faint card-row appears once bound
    ui.clear_all()

    while True:
        # Short-deadline card read — keeps the loop responsive without
        # hammering the I2C bus. read_card() polls every ~100 ms anyway.
        card = wand.read_card(timeout_ms=poll_ms, animate=False)
        if card is None:
            # Brief sleep so other I2C-using code (e.g., later programming
            # blocks reading the accel) can get a turn.
            time.sleep_ms(30)
            continue

        color, serial = card

        # ── Card-lock check ──────────────────────────────────
        if wand.bound_card is None:
            # First tap of the session — bind and scan
            wand.bound_card = (color, serial)
            ui.set_card_color(color)
            wand.beep(1500, 60)
            ui.vibrate(50)
            ui.card_tap_intro(ms=300)
            new_conns = _scan_and_connect(
                wand, ble, color, serial,
                existing=wand.connections,
                scan_ms=scan_ms, slot_prefix=slot_prefix,
                on_data=on_data)
            wand.connections.extend(new_conns)

        elif wand.bound_card == (color, serial):
            # Same card again — re-scan, add new devices
            wand.beep(1500, 60)
            ui.vibrate(50)
            ui.card_tap_intro(ms=200)
            new_conns = _scan_and_connect(
                wand, ble, color, serial,
                existing=wand.connections,
                scan_ms=scan_ms, slot_prefix=slot_prefix,
                on_data=on_data)
            wand.connections.extend(new_conns)

        else:
            # Wrong card — reject with audio + double buzz, no scan.
            # Don't change bound_card, don't touch row 4, don't scan.
            wand.beep(300, 120)
            ui.vibrate_pattern([(30, 60), (30, 0)])
            time.sleep_ms(300)   # short — user might immediately try the right card
            continue

        # Settle delay so a card still held over the reader doesn't
        # immediately retrigger another scan
        time.sleep_ms(800)