# runloop.py — top-level state machine for the wand programming system.
#
# Reactive (event-based) programming model:
#   - The deck is a list of RULES, each is {'event': opcode, 'body': [opcodes]}.
#   - Tapping an EVENT card starts a new rule.
#   - Tapping any non-event programming card joins the current rule's body.
#   - Tapping GO enters the event loop: every loop iteration polls each
#     rule's event; when a rule's event fires on its rising edge, its
#     body runs sequentially. Only one body runs at a time.
#   - Tapping STOP (or any pairing card) during execution exits the loop.
#
# States:
#   PAIRING_IDLE — no devices connected. Tap pairing card to pair.
#   PAIRED_IDLE  — devices connected, no rules yet.
#   PROGRAMMING  — assembling rules.
#   RUNNING      — event loop is active.

import time

from cardpair import _scan_and_connect, _get_or_make_ui
from program_cards import (
    lookup, is_pairing_card, is_event, category_color,
    read_card_universal,
    CAT_META, CAT_MOTION, CAT_SENSING, CAT_EVENT, CAT_CONTROL)
from program_runtime import execute_event_loop
from wand_ui import MAX_DEVICES
from newhub import SINGLE_MOTOR, DOUBLE_MOTOR, COLOR_SENSOR, CONTROLLER


# Maps opcode 'op' field → required product_id (or None = no device needed)
_OP_REQUIRES = {
    # Double motor ops
    'keep_moving':  DOUBLE_MOTOR,
    'stop_double':  DOUBLE_MOTOR,
    'turn':         DOUBLE_MOTOR,
    'move':         DOUBLE_MOTOR,
    # Single motor ops
    'run_single':   SINGLE_MOTOR,
    'stop_single':  SINGLE_MOTOR,
    'single_angle': SINGLE_MOTOR,
    # Color sensor events
    'check_color':  COLOR_SENSOR,
    # Controller events
    'check_controller': CONTROLLER,
}


def _required_device(opcode):
    """Return the product_id required by this opcode, or None."""
    return _OP_REQUIRES.get(opcode.get('op'))


def _device_connected(wand, product_id):
    """Return True if at least one device with product_id is connected."""
    for _slot, _hub, info in wand.connections:
        if info.get('product_id') == product_id:
            return True
    return False


_DEVICE_NAMES = {
    SINGLE_MOTOR: 'Single Motor',
    DOUBLE_MOTOR: 'Double Motor',
    COLOR_SENSOR: 'Color Sensor',
    CONTROLLER:   'Controller',
}


STATE_PAIRING_IDLE = 'pairing_idle'
STATE_PAIRED_IDLE  = 'paired_idle'
STATE_PROGRAMMING  = 'programming'
STATE_RUNNING      = 'running'

MAX_RULES = 4   # one row per rule (rows 1..4 on the 5x5 grid)
MAX_BODY  = 4   # how many actions per rule




def _find_rule_with_event(rules, event_opcode):
    """Search ``rules`` for a rule whose event matches ``event_opcode``
    (same ``op`` and same ``args``). Returns the index or None.
    Used for event-replacement when the user re-taps an event card."""
    target_op = event_opcode.get('op')
    target_args = event_opcode.get('args', {}) or {}
    for i, rule in enumerate(rules):
        ev = rule['event']
        if ev.get('op') != target_op:
            continue
        if (ev.get('args', {}) or {}) == target_args:
            return i
    return None




def run_program_loop(wand, ble, scan_ms=700, on_data=None, poll_ms=100):
    """Top-level loop. Forever:
      PAIRING_IDLE → PAIRED_IDLE → PROGRAMMING → RUNNING → PROGRAMMING ...

    State on the wand:
        wand.bound_card  – pairing card (color, serial), or None
        wand.connections – list of (slot, hub, info)
        wand.program     – list of {'event': opcode, 'body': [opcodes]}
    """

    ui = _get_or_make_ui(wand)
    wand.connections = getattr(wand, 'connections', [])
    wand.bound_card  = getattr(wand, 'bound_card',  None)
    wand.program     = getattr(wand, 'program',     [])

    state = STATE_PAIRING_IDLE if wand.bound_card is None else STATE_PAIRED_IDLE
    ui.clear_all()

    while True:
        card = read_card_universal(wand, timeout_ms=poll_ms)
        if card is None:
            if state == STATE_PAIRING_IDLE:
                ui.tick_idle()
            time.sleep_ms(30)
            continue

        color, serial = card
        print("tap: color={} serial={}".format(color, serial))

        opcode = lookup(serial)

        if opcode is None and is_pairing_card(serial):
            print("  → pairing card")
            _handle_pairing_card(wand, ble, ui, color, serial, state,
                                 scan_ms, on_data)
            state = STATE_PAIRED_IDLE if wand.bound_card else STATE_PAIRING_IDLE

        elif opcode is not None:
            print("  → program card: {}".format(opcode['name']))
            # Battery check works anytime — bypass the pairing gate
            if opcode.get('op') == 'battery':
                _handle_battery(wand, ui)
            else:
                new_state = _handle_program_card(wand, ble, ui, opcode, state,
                                                 on_data=on_data, scan_ms=scan_ms)
                if new_state is not None:
                    state = new_state

        else:
            print("  → unknown card")
            wand.beep(300, 120)
            ui.vibrate_pattern([(30, 60), (30, 0)])

        # Settle so a held card doesn't immediately retrigger
        if state == STATE_PROGRAMMING:
            time.sleep_ms(250)
        else:
            time.sleep_ms(800)


# ── Card handlers ────────────────────────────────────────────────────

def _handle_battery(wand, ui):
    """Read and display battery level. Works at any time, no pairing required."""
    try:
        soc = wand.battery.soc
        print("  battery: {:.1f}%".format(soc))
    except Exception as e:
        print("  battery: read failed ({})".format(e))
        soc = 0
    ui.show_battery(soc)
    ui.paint_deck(wand.program)   # restore deck view after display

def _handle_pairing_card(wand, ble, ui, color, serial, state,
                         scan_ms, on_data):
    """Pairing card was tapped. Only allowed in PAIRING_IDLE or
    PAIRED_IDLE-with-matching-card. Other states: reject."""
    if state in (STATE_PROGRAMMING, STATE_RUNNING):
        wand.beep(300, 120)
        ui.vibrate_pattern([(30, 60), (30, 0)])
        return

    if wand.bound_card is None:
        wand.bound_card = (color, serial)
        ui.set_card_color(color)
        wand.beep(1500, 60)
        ui.vibrate(50)
        ui.card_tap_intro(ms=300)
        new_conns = _scan_and_connect(wand, ble, color, serial,
                                      existing=wand.connections,
                                      scan_ms=scan_ms, on_data=on_data)
        wand.connections.extend(new_conns)

    elif wand.bound_card == (color, serial):
        wand.beep(1500, 60)
        ui.vibrate(50)
        ui.card_tap_intro(ms=200)
        new_conns = _scan_and_connect(wand, ble, color, serial,
                                      existing=wand.connections,
                                      scan_ms=scan_ms, on_data=on_data)
        wand.connections.extend(new_conns)
    else:
        wand.beep(300, 120)
        ui.vibrate_pattern([(30, 60), (30, 0)])


def _handle_program_card(wand, ble, ui, opcode, state,
                         on_data=None, scan_ms=700):
    """Programming card was tapped. Returns the new state, or None to
    keep state unchanged."""
    if wand.bound_card is None:
        # Can't program without devices
        wand.beep(300, 120)
        ui.vibrate_pattern([(30, 60), (30, 0)])
        return None

    op = opcode.get('op')

    # ── META cards ───────────────────────────────────────────
    if op == 'erase':
        wand.program = []
        ui.vibrate(80)
        ui.wipe_anim((10, 0, 0))
        return STATE_PROGRAMMING

    if op == 'go':
        if not wand.program:
            wand.beep(400, 150)
            ui.vibrate(40)
            return None
        wand.beep(2000, 100)
        ui.vibrate(80)
        ui.flash_anim(flashes=2)
        _execute_with_visuals(wand, ble, ui)
        ui.flash_anim(flashes=1)
        ui.paint_deck(wand.program)
        return STATE_PROGRAMMING

    if op == 'program_mode':
        ui.vibrate(40)
        ui.paint_deck(wand.program)
        return STATE_PROGRAMMING

    if op == 'stop':
        # STOP halts execution and returns to programming mode.
        # Program is preserved — tap ERASE to clear it.
        wand.beep(800, 80)
        ui.vibrate(50)
        ui.paint_deck(wand.program)
        return STATE_PROGRAMMING

    # ── EVENT or BODY card — append to deck ───────────────────
    # Check required device is connected before accepting
    req = _required_device(opcode)
    if req is not None and not _device_connected(wand, req):
        name = _DEVICE_NAMES.get(req, 'device')
        print("  {} not connected — ignoring card".format(name))
        wand.beep(600, 80); time.sleep_ms(60); wand.beep(400, 120)
        ui.vibrate_pattern([(20, 40), (20, 0)])
        return None

    if is_event(opcode):
        # Does this event card already exist in the deck? If so, the
        # user is "editing" that rule — remove the old one and append
        # a fresh empty rule. New action cards then build it up.
        existing_idx = _find_rule_with_event(wand.program, opcode)
        if existing_idx is not None:
            print("  re-tapping event — replacing rule {}".format(existing_idx))
            wand.program.pop(existing_idx)
            # Fall through to append below
        if len(wand.program) >= MAX_RULES:
            print("  deck full ({} rules max)".format(MAX_RULES))
            wand.beep(300, 120)
            ui.vibrate_pattern([(30, 60), (30, 0)])
            return None
        wand.program.append({'event': opcode, 'body': []})
        wand.beep(1800, 40)
        ui.vibrate(40)
        ui.flash_block_ack(category_color(opcode))
        ui.paint_deck(wand.program)
        return STATE_PROGRAMMING

    # Non-event action card — must follow an event card
    if not wand.program:
        print("  body card needs an event card first")
        wand.beep(300, 200)
        ui.vibrate_pattern([(30, 60), (30, 0)])
        return None

    current_rule = wand.program[-1]
    if len(current_rule['body']) >= MAX_BODY:
        print("  rule body full ({} actions max)".format(MAX_BODY))
        wand.beep(300, 120)
        ui.vibrate_pattern([(30, 60), (30, 0)])
        return None

    current_rule['body'].append(opcode)
    wand.beep(1800, 40)
    ui.vibrate(40)
    ui.flash_block_ack(category_color(opcode))
    ui.paint_deck(wand.program)
    return STATE_PROGRAMMING


# ── Execution ────────────────────────────────────────────────────────

def _arm_motors(wand):
    """Wake up every connected motor by issuing the LEGO-required
    'speed=0 + run' sequence. Without this priming, the first
    motor_speed/motor_run command after pairing can be ignored — the
    motor needs to be 'armed' once before it responds.

    Called before each event-loop run, so even if pairing happened a
    long time ago or the auto-arm in on_data missed the first packet,
    we guarantee the motor is ready when GO is tapped."""
    from newhub import SINGLE_MOTOR, DOUBLE_MOTOR
    for slot, hub, info in wand.connections:
        pid = info.get('product_id')
        try:
            if pid == SINGLE_MOTOR:
                hub.motor_speed(1, 0)
                hub.motor_run(1, 0)
                print("  armed single motor on slot '{}'".format(slot))
            elif pid == DOUBLE_MOTOR:
                hub.motor_speed(3, 0)
                hub.motor_run(3, 0)
                print("  armed double motor on slot '{}'".format(slot))
        except Exception as e:
            print("  arm error on slot '{}':".format(slot), e)


def _execute_with_visuals(wand, ble, ui):
    """Wrap execute_event_loop with LED feedback. Sets up an
    on_card_during_run callback that stops execution on STOP / pairing.
    If stopped via STOP card, the program is also erased."""

    # Captured in closure so _on_card can set it and the caller can read it
    stop_reason = ['none']

    def _on_card(card):
        """Called by the event loop when ANY card is tapped during run.
        Return True to halt the loop."""
        color, serial = card
        op = lookup(serial)
        # STOP card — halt execution, keep program intact
        if op is not None and op.get('op') == 'stop':
            print("  STOP card tapped — halting program")
            stop_reason[0] = 'stop'
            return True
        # BATTERY card — show level then resume (non-halting)
        if op is not None and op.get('op') == 'battery':
            try:
                soc = wand.battery.soc
                print("  battery: {:.1f}%".format(soc))
            except Exception:
                soc = 0
                print("  battery: read failed")
            ui.show_battery(soc, hold_ms=3000)
            ui.paint_running(wand.program, -1)   # restore display, no rule firing
            return False   # don't halt execution
        # Pairing card — stops but keeps the program intact
        if op is None and is_pairing_card(serial):
            print("  pairing card tapped — halting program")
            stop_reason[0] = 'pairing'
            return True
        # Anything else (program cards during running) — ignore
        return False

    def _on_rule_fire(rule_idx):
        # Brief LED cue: highlight the firing rule row.
        ui.paint_running(wand.program, rule_idx)

    print("event loop starting — {} rule(s) armed".format(len(wand.program)))
    _arm_motors(wand)
    ui.paint_running(wand.program, -1)   # show all rules dim while waiting
    try:
        execute_event_loop(wand.program, wand, ble, wand.connections,
                           on_card_during_run=_on_card,
                           on_rule_fire=_on_rule_fire, ui=ui)
    except Exception as e:
        print("event loop error:", e)

    # Post-loop: restore deck display (program is preserved)
    print("event loop stopped (reason={})".format(stop_reason[0]))
    ui.paint_deck(wand.program)