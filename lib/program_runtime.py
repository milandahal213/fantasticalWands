# program_runtime.py — executes an assembled program.
#
# A program is a list of opcode dicts (the values from program_cards.OPCODES).
# Each opcode dispatches by its 'op' string to a handler in OP_HANDLERS.
#
# Handlers receive (ctx, args):
#   ctx  : a SimpleNamespace with .wand, .ble, .connections, .stop
#   args : the opcode's 'args' dict, or {}
#
# Handlers should respect ctx.stop[0] (a 1-element list — set to True by
# the runtime if the user button-stops execution). If True, return early.
#
# Motor mapping convention:
#   Double motor: LEFT = port 1, RIGHT = port 2, BOTH = port 3.
#   Single motor: PORT_SINGLE = 1.
#   See LEGO API: motor_speed, motor_run, motor_angle.

import time
from newhub import SINGLE_MOTOR, DOUBLE_MOTOR, COLOR_SENSOR, CONTROLLER
from program_cards import (
    DIR_FORWARD, DIR_BACKWARD, DIR_LEFT, DIR_RIGHT, DIR_CW, DIR_CCW)


# LEGO motor port constants
MOTOR_LEFT  = 1
MOTOR_RIGHT = 2
MOTOR_BOTH  = 3
PORT_SINGLE = 1

# LEGO motor_run direction codes (from newhub.motor_run)
MOTOR_DIR_CW   = 0    # clockwise (varies by motor mount)
MOTOR_DIR_STOP = 1
MOTOR_DIR_CCW  = 2    # counter-clockwise

# Default motor speed for any block that doesn't specify one (0..100)
DEFAULT_SPEED = 50

# Step size in degrees per "step" unit (Q&A: 1 step = 1 motor rotation = 360°)
STEP_DEGREES = 360


def _find_first(connections, product_id):
    """Return the (slot, hub, info) for the first connected device of
    the given product id, or None if none connected."""
    for slot, hub, info in connections:
        if info.get('product_id') == product_id:
            return slot, hub, info
    return None


# ── Handlers ─────────────────────────────────────────────────────────

def op_wait_button(ctx, args):
    """Block until the wand's button is pressed (active-low)."""
    while ctx.wand.button.value() == 1:
        if ctx.stop[0]: return
        time.sleep_ms(20)
    # Debounce: wait for release
    while ctx.wand.button.value() == 0:
        time.sleep_ms(20)


def op_wait_shake(ctx, args):
    """Block until wand motion exceeds threshold."""
    accel = ctx.wand.accel
    prev = accel.read()
    score = 0.0
    while True:
        if ctx.stop[0]: return
        try:
            x, y, z = accel.read()
        except Exception:
            time.sleep_ms(20); continue
        delta = abs(x - prev[0]) + abs(y - prev[1]) + abs(z - prev[2])
        prev = (x, y, z)
        # Same EMA-smoothed score as RepairTrigger had
        score = 0.5 * delta + 0.5 * score
        if score > 0.25:
            return
        time.sleep_ms(20)


def op_wait_color(ctx, args):
    """Block until the connected color sensor reports ``args['color']``.
    Does nothing (returns immediately) if no color sensor is connected."""
    target = args.get('color')
    if target is None: return

    found = _find_first(ctx.connections, COLOR_SENSOR)
    if found is None:
        print("wait_color: no color sensor connected, skipping")
        return
    _slot, hub, _info = found

    while True:
        if ctx.stop[0]: return
        observed = hub.data.get('color')
        if observed == target:
            return
        time.sleep_ms(50)


def _drive_double(hub, left_speed, right_speed):
    """Set both motor speeds on a double motor hub."""
    hub.motor_speed(MOTOR_LEFT,  left_speed)
    hub.motor_speed(MOTOR_RIGHT, right_speed)


def _wait_for_double_motor_distance(ctx, hub, target_degrees):
    """Block until BOTH motors have moved at least target_degrees from
    their current position. Polls ctx.stop[0] every iteration; returns
    early if set. Uses motor telemetry from hub.data."""
    # Take starting positions
    start1 = hub.data.get('position1', 0)
    start2 = hub.data.get('position2', 0)
    deadline = time.ticks_ms() + 10000   # 10 s safety cap
    while True:
        if ctx.stop[0]:
            return
        p1 = hub.data.get('position1', start1)
        p2 = hub.data.get('position2', start2)
        if abs(p1 - start1) >= target_degrees and abs(p2 - start2) >= target_degrees:
            return
        if time.ticks_diff(time.ticks_ms(), deadline) > 0:
            return
        time.sleep_ms(30)


def op_move(ctx, args):
    """Drive the double motor forward/back/left/right for ``args['steps']``
    motor rotations.

    Falls through silently if no double motor is connected — single
    motors get the analogous 'run' handling."""
    steps = args.get('steps', 1)
    direction = args.get('dir', DIR_FORWARD)
    target_deg = steps * STEP_DEGREES

    dm = _find_first(ctx.connections, DOUBLE_MOTOR)
    if dm is not None:
        _slot, hub, _info = dm
        print("  move: {} steps {} on slot '{}' (target {}°)".format(
            steps, direction, _slot, target_deg))
        # Map direction to left/right speeds (LEFT motor mounted reversed
        # so forward = +left, +right doesn't work without sign trick.
        # Match Examples/7ControllerDoubleMotor: tank drive inverts LEFT.)
        speed = DEFAULT_SPEED
        if direction == DIR_FORWARD:
            l, r = -speed,  speed
        elif direction == DIR_BACKWARD:
            l, r =  speed, -speed
        elif direction == DIR_LEFT:    # rotate in place left
            l, r =  speed,  speed
        elif direction == DIR_RIGHT:   # rotate in place right
            l, r = -speed, -speed
        else:
            l, r = 0, 0
        _drive_double(hub, l, r)
        _wait_for_double_motor_distance(ctx, hub, target_deg)
        # Halt: speed=0 AND motor_stop, like op_stop_double does.
        # This is the same belt-and-suspenders approach because bounded
        # actions also need to RELIABLY stop at completion.
        _drive_double(hub, 0, 0)
        try: hub.motor_stop(MOTOR_BOTH)
        except: pass
        return

    # Fallback: a single motor — just spin it
    sm = _find_first(ctx.connections, SINGLE_MOTOR)
    if sm is not None:
        _slot, hub, _info = sm
        speed = DEFAULT_SPEED
        if direction in (DIR_BACKWARD, DIR_LEFT, DIR_CCW):
            speed = -speed
        hub.motor_speed(PORT_SINGLE, speed)
        # ~1 rotation/sec at speed 50. Poll for stop every 30 ms so
        # STOP card halts the motion mid-rotation.
        deadline = time.ticks_ms() + int(steps * 1000)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if ctx.stop[0]: break
            time.sleep_ms(30)
        hub.motor_speed(PORT_SINGLE, 0)


def op_turn(ctx, args):
    """Turn in place by ``args['degrees']`` using timed differential drive.
    
    Uses motor_speed with opposite wheel directions for a calibrated duration.
    Similar to op_single_angle's timed approach.
    """
    degrees = args.get('degrees', 90)
    direction = args.get('dir', DIR_CW)

    dm = _find_first(ctx.connections, DOUBLE_MOTOR)
    if dm is None:
        print("  turn: NO DOUBLE MOTOR CONNECTED")
        return
    _slot, hub, _info = dm
    
    # Calibration: milliseconds per degree of robot rotation
    # This needs empirical tuning based on wheel spacing and motor speed
    # At speed=50, estimate ~500ms for 90° turn → ~5.5ms per degree
    MS_PER_DEGREE = 3.5  # empirical: 90° turn takes ~315ms at speed 50
    
    duration_ms = int(degrees * MS_PER_DEGREE)
    speed = DEFAULT_SPEED
    
    print("  turn: {}° {} on slot '{}' ({}ms @ speed {})".format(
        degrees, direction, _slot, duration_ms, speed))
    
    # Tank drive: opposite motor speeds for in-place rotation
    if direction == DIR_CW:
        # Right turn: both motors = -speed
        hub.motor_speed(MOTOR_LEFT, -speed)
        hub.motor_speed(MOTOR_RIGHT, -speed)
    else:
        # Left turn: both motors = +speed
        hub.motor_speed(MOTOR_LEFT, speed)
        hub.motor_speed(MOTOR_RIGHT, speed)
    
    # Wait for the calibrated duration (with ctx.stop checks)
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
        if ctx.stop[0]:
            hub.motor_stop(MOTOR_BOTH)
            print("  turn: stopped by user")
            return
        time.sleep_ms(20)
    
    # Stop motors and clear cache so keep_moving will resend if triggered
    hub.motor_speed(MOTOR_LEFT, 0)
    hub.motor_speed(MOTOR_RIGHT, 0)
    hub.motor_stop(MOTOR_BOTH)
    hub.data['_last_speed_sent'] = (0, 0)
    
    print("  turn: complete")


def op_run(ctx, args):
    """Run a single motor for ``args['rotations']`` rotations in the
    given direction. Blocks until the motor completes its rotation."""
    rotations = args.get('rotations', 1)
    direction = args.get('dir', DIR_CW)
    target_deg = rotations * STEP_DEGREES

    sm = _find_first(ctx.connections, SINGLE_MOTOR)
    if sm is not None:
        _slot, hub, _info = sm
        motor_dir = MOTOR_DIR_CW if direction == DIR_CW else MOTOR_DIR_CCW
        start = hub.data.get('position1', 0)
        hub.motor_angle(PORT_SINGLE, target_deg, motor_dir)
        # Wait for position to advance by ~target_deg, with safety cap
        deadline = time.ticks_ms() + (target_deg * 10) + 2000
        interrupted = False
        while True:
            if ctx.stop[0]:
                interrupted = True; break
            p = hub.data.get('position1', start)
            if abs(p - start) >= target_deg: break
            if time.ticks_diff(time.ticks_ms(), deadline) > 0: break
            time.sleep_ms(30)
        # If we were interrupted mid-rotation, motor_angle is still
        # running — explicitly stop it.
        if interrupted:
            try: hub.motor_stop(PORT_SINGLE)
            except: pass
        return

    # Fall back to driving one wheel of a double motor
    dm = _find_first(ctx.connections, DOUBLE_MOTOR)
    if dm is not None:
        _slot, hub, _info = dm
        motor_dir = MOTOR_DIR_CW if direction == DIR_CW else MOTOR_DIR_CCW
        start = hub.data.get('position2', 0)
        hub.motor_angle(MOTOR_RIGHT, target_deg, motor_dir)
        deadline = time.ticks_ms() + (target_deg * 10) + 2000
        interrupted = False
        while True:
            if ctx.stop[0]:
                interrupted = True; break
            p = hub.data.get('position2', start)
            if abs(p - start) >= target_deg: break
            if time.ticks_diff(time.ticks_ms(), deadline) > 0: break
            time.sleep_ms(30)
        if interrupted:
            try: hub.motor_stop(MOTOR_RIGHT)
            except: pass


# ── New motion handlers (continuous / stop / single-motor) ──────────

def op_keep_moving(ctx, args):
    """Start both motors continuously in ``args['dir']`` and return.
    NON-BLOCKING. The motors keep running until 'stop_double' or another
    motor command countermands. Body advances immediately.

    Deduplicates redundant sends (see op_run_single for why)."""
    direction = args.get('dir', DIR_FORWARD)
    dm = _find_first(ctx.connections, DOUBLE_MOTOR)
    if dm is None:
        print("  keep_moving: NO DOUBLE MOTOR CONNECTED")
        return
    _slot, hub, _info = dm
    speed = DEFAULT_SPEED
    if direction == DIR_FORWARD:
        l, r = -speed,  speed   # tank drive: left inverted
    elif direction == DIR_BACKWARD:
        l, r =  speed, -speed
    else:
        l, r = 0, 0

    # Deduplicate
    last = hub.data.get('_last_speed_sent')
    if last == (l, r):
        print("  keep_moving: {} on slot '{}' (already at this speed)".format(
            direction, _slot))
        return

    print("  keep_moving: {} on slot '{}' (L={} R={})".format(
        direction, _slot, l, r))
    _drive_double(hub, l, r)
    hub.data['_last_speed_sent'] = (l, r)
    # NB: deliberately no wait — return immediately so next body action
    # can run while motors keep spinning.


def op_stop_double(ctx, args):
    """Stop both motors of the double motor."""
    dm = _find_first(ctx.connections, DOUBLE_MOTOR)
    if dm is None:
        print("  stop_double: NO DOUBLE MOTOR CONNECTED")
        return
    _slot, hub, _info = dm
    print("  stop_double: slot '{}'".format(_slot))
    # Belt-and-suspenders: set speed to 0 AND send motor_stop.
    # Either alone usually halts the motors, but the LEGO API has
    # quirks around which start-method (speed vs run vs angle) responds
    # to which stop-method. Doing both is safest.
    try: hub.motor_speed(MOTOR_LEFT,  0)
    except: pass
    try: hub.motor_speed(MOTOR_RIGHT, 0)
    except: pass
    try: hub.motor_stop(MOTOR_BOTH)
    except: pass
    # Clear cached speed so next keep_moving will resend the command
    hub.data['_last_speed_sent'] = (0, 0)


def op_single_angle(ctx, args):
    """Rotate the single motor approximately ``args['degrees']`` in
    ``args['dir']``.

    Implementation note: tests showed motor_angle() significantly
    under-delivers (asked for 360°, motor moved 288°; asked for 90°,
    motor moved ~20°). It also produces an audible "click" without
    much rotation. So we use motor_speed + a timed stop instead, which
    is reliable.

    Empirically, motor_speed(1, 50) gives roughly 280°/sec, so
    we compute a duration from the requested degrees.

    This BRIEFLY blocks (~300ms for 90°) but that's short enough that
    event polling isn't visibly affected."""
    degrees = args.get('degrees', 90)
    direction = args.get('dir', DIR_CW)

    sm = _find_first(ctx.connections, SINGLE_MOTOR)
    if sm is None:
        print("  single_angle: NO SINGLE MOTOR CONNECTED")
        return
    _slot, hub, _info = sm
    print("  single_angle: {}° {} on slot '{}'".format(
        degrees, direction, _slot))

    # ~280°/sec at speed 50 → convert degrees to milliseconds
    DEGREES_PER_SEC_AT_50 = 78   # empirical: measured on hardware at speed 50
    duration_ms = int(degrees * 1000 / DEGREES_PER_SEC_AT_50)

    speed = DEFAULT_SPEED
    if direction == DIR_CCW:
        speed = -speed

    hub.motor_speed(PORT_SINGLE, speed)
    hub.data['_last_speed_sent'] = speed
    # Brief polling sleep so STOP can interrupt
    deadline = time.ticks_ms() + duration_ms
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if ctx.stop[0]: break
        time.sleep_ms(20)
    hub.motor_speed(PORT_SINGLE, 0)
    hub.data['_last_speed_sent'] = 0  # Clear cache — motor is now stopped


def op_run_single(ctx, args):
    """Run the single motor continuously in ``args['dir']`` and return.
    NON-BLOCKING. Body advances immediately.

    Important: only sends the motor_speed BLE command if the desired
    speed differs from the last-sent speed. Sending the same
    motor_speed repeatedly (e.g. when an event fires many times)
    causes the LEGO single motor to STALL instead of run — each call
    seems to reset the motion. So we deduplicate."""
    direction = args.get('dir', DIR_CW)
    sm = _find_first(ctx.connections, SINGLE_MOTOR)
    if sm is None:
        print("  run_single: NO SINGLE MOTOR CONNECTED")
        return
    _slot, hub, _info = sm

    speed = DEFAULT_SPEED
    if direction == DIR_CCW:
        speed = -speed

    # Deduplicate: only send the BLE command if speed actually changed
    last = hub.data.get('_last_speed_sent')
    if last == speed:
        print("  run_single: {} on slot '{}' (already at this speed)".format(
            direction, _slot))
        return

    print("  run_single: {} on slot '{}' (speed {})".format(
        direction, _slot, speed))
    hub.motor_speed(PORT_SINGLE, speed)
    hub.data['_last_speed_sent'] = speed


def op_stop_single(ctx, args):
    """Stop the single motor."""
    sm = _find_first(ctx.connections, SINGLE_MOTOR)
    if sm is None:
        print("  stop_single: NO SINGLE MOTOR CONNECTED")
        return
    _slot, hub, _info = sm
    print("  stop_single: slot '{}'".format(_slot))
    # Belt-and-suspenders — both speed-zero and motor_stop
    try: hub.motor_speed(PORT_SINGLE, 0)
    except: pass
    try: hub.motor_stop(PORT_SINGLE)
    except: pass
    # Clear cached speed so next run_single will resend the command
    hub.data['_last_speed_sent'] = 0


# ── Dispatch table ──────────────────────────────────────────────────

OP_HANDLERS = {
    # Double motor
    'move':        op_move,
    'turn':        op_turn,
    'keep_moving': op_keep_moving,
    'stop_double': op_stop_double,
    # Single motor
    'single_angle': op_single_angle,
    'run_single':   op_run_single,
    'stop_single':  op_stop_single,
}


class _Ctx:
    """Tiny context passed to handlers. Plain class (MicroPython has no
    SimpleNamespace)."""
    def __init__(self, wand, ble, connections, stop):
        self.wand        = wand
        self.ble         = ble
        self.connections = connections
        self.stop        = stop



# ── Event pollers (non-blocking, edge-triggered) ────────────────────
#
# These return True only on a rising edge — when the condition just
# became true since the last call. State is kept per-rule in ctx, in a
# dict keyed by id(opcode) so each rule has its own memory.
#
# Each poller signature: (ctx, args, state) -> bool
#   state: a dict you can stash 'last' into across calls

def check_button(ctx, args, state):
    """Fires when the wand button transitions to pressed."""
    now = ctx.wand.button.value() == 0
    fired = now and not state.get('last', False)
    state['last'] = now
    if fired:
        print("event fired: button pressed")
    return fired


def check_shake(ctx, args, state):
    """Fires when sustained motion accumulates over a short window.

    Approach (replaces previous jerk-counting logic):
      - Track a 500ms ring buffer of motion deltas
      - Sum them = 'window' = total recent motion energy
      - Fire when window first crosses ACTIVATE (rising edge)
      - Don't fire again until window has dropped below RELEASE
        (this hysteresis prevents the natural decay-tail of one
        shake from being mistaken for a second shake)

    Tuned from shake_probe2.py data:
      - Rest:            window ~0.0 - 0.04
      - Casual handling: window ~1 - 5
      - Real shake:      window peaks 25 - 100
    """
    accel = ctx.wand.accel
    try:
        x, y, z = accel.read()
    except Exception:
        return False

    prev = state.get('prev')
    if prev is None:
        state['prev']       = (x, y, z)
        state['deltas']     = []
        state['was_active'] = False
        return False

    delta = abs(x - prev[0]) + abs(y - prev[1]) + abs(z - prev[2])
    state['prev'] = (x, y, z)

    # Tunables: see shake_probe2.py for the empirical basis
    SAMPLES_IN_WINDOW = 10    # 10 samples × ~25 ms loop = 250 ms window
    ACTIVATE          = 12.0  # window must climb past this to fire
    RELEASE           = 2.0   # ...and drop back below this before next fire

    deltas = state['deltas']
    deltas.append(delta)
    if len(deltas) > SAMPLES_IN_WINDOW:
        deltas.pop(0)
    window = sum(deltas)

    was_active = state['was_active']

    # Re-arm: motion subsided enough that we'd recognize a new shake
    if was_active and window < RELEASE:
        state['was_active'] = False
        return False

    # Fire: motion just crossed the activation bar
    if (not was_active) and window > ACTIVATE:
        state['was_active'] = True
        print("event fired: shake (window={:.1f})".format(window))
        return True

    return False


def check_color(ctx, args, state):
    """Fires when the color sensor's reported color first matches
    ``args['color']`` after being something else."""
    target = args.get('color')
    found = _find_first(ctx.connections, COLOR_SENSOR)
    if found is None:
        return False
    _slot, hub, _info = found
    observed = hub.data.get('color')
    is_target = (observed == target)
    fired = is_target and not state.get('was_target', False)
    state['was_target'] = is_target
    if fired:
        # 6=green, 9=red, etc. Name them for clarity in the log.
        names = {6: 'GREEN', 9: 'RED', 3: 'BLUE', 7: 'YELLOW'}
        print("event fired: color {} detected".format(
            names.get(target, target)))
    return fired


def check_controller(ctx, args, state):
    """Fires when a controller joystick is pushed FULLY into its extreme.

    args:
        side : 'left' or 'right'
        dir  : +1 (positive extreme) or -1 (negative extreme)

    Empirically (from tools/controller_probe.py):
      - leftAngle / rightAngle peak around +/-4500, not +/-100
      - There's ~50 of drift at rest, so anything near zero is noise
      - *Step values are just *Angle scaled by ~1/45, NOT discrete detents

    To prevent retriggering from noise, we use hysteresis:
      - ACTIVATE: angle past +/-3500 → arm + fire
      - RELEASE:  angle inside +/-1500 → disarm (ready to fire again)

    Joystick must fully return toward center before another fire."""
    found = _find_first(ctx.connections, CONTROLLER)
    if found is None:
        return False
    _slot, hub, _info = found

    side = args.get('side', 'left')
    direction = args.get('dir', 1)
    key = 'leftAngle' if side == 'left' else 'rightAngle'
    angle = hub.data.get(key)
    if angle is None:
        return False

    ACTIVATE = 3500   # how committed the joystick has to be to fire
    RELEASE  = 1500   # how close to center before we re-arm

    # Direction-aware activation test
    if direction > 0:
        beyond_activate = angle > ACTIVATE
        inside_release  = angle < RELEASE
    else:
        beyond_activate = angle < -ACTIVATE
        inside_release  = angle > -RELEASE

    was_active = state.get('was_active', False)

    # Re-arm when joystick returns near center
    if was_active and inside_release:
        state['was_active'] = False
        return False

    # Fire when joystick first reaches the extreme
    if (not was_active) and beyond_activate:
        state['was_active'] = True
        print("event fired: {} joystick = {:+d} (angle={})".format(
            side, direction, angle))
        return True

    return False


POLLERS = {
    'check_button':     check_button,
    'check_shake':      check_shake,
    'check_color':      check_color,
    'check_controller': check_controller,
}


# ── Body executor (runs the action list when a rule fires) ──────────

def _run_body(body, ctx, ui=None, rule_idx=None, rule_colors=None):
    """Run a single rule's body opcodes sequentially. Each opcode
    dispatches to its blocking handler (the OP_HANDLERS table).
    Respects ctx.stop[0]; returns early if set."""
    for opcode in body:
        if ctx.stop[0]: return
        handler = OP_HANDLERS.get(opcode.get('op'))
        if handler is None:
            print("Unknown body op:", opcode.get('op'))
            continue
        try:
            handler(ctx, opcode.get('args', {}))
        except Exception as e:
            print("body handler error:", e)


# ── Event loop ──────────────────────────────────────────────────────

def execute_event_loop(rules, wand, ble, connections,
                       on_card_during_run=None,
                       on_rule_fire=None, ui=None,
                       loop_ms=25):
    """Run the assembled rules as an event loop.

    Args:
        rules                  – list of {'event': opcode, 'body': [opcodes]}
        wand                   – Wand instance
        ble                    – BLEDevice
        connections            – wand.connections
        on_card_during_run(card)
                               – optional. If provided, called when a card
                                 is tapped during execution. Returning True
                                 from the callback stops the loop. (Used
                                 by runloop.py to detect STOP / pairing.)
        on_rule_fire(rule_idx) – optional callback when a rule fires.
                                 Use it to drive the LED execution cursor.
        ui                     – optional WandUI (unused at runtime now;
                                 reserved for future cursor display).
        loop_ms                – iteration period. Lower = snappier events,
                                 more CPU.

    Returns when stopped via on_card_during_run or KeyboardInterrupt."""
    from program_cards import read_card_universal

    stop = [False]
    ctx = _Ctx(wand, ble, connections, stop)

    # Per-rule poller state. Same length as rules; each entry is a
    # mutable dict the poller can stash its 'last' value in.
    rule_states = [{} for _ in rules]

    # Throttle NFC card polling. The PN532 read is synchronous and
    # holds the I²C bus for ~20-50ms; doing it every loop iteration
    # starves BLE writes (visible as motor commands becoming clicks
    # instead of motion). Once every 5 iterations (~125ms at loop_ms=25)
    # is plenty fast for STOP-card detection while leaving BLE alone.
    CARD_POLL_EVERY = 5
    card_poll_counter = 0

    while not stop[0]:
        # 1. Check for cards (STOP / pairing card from the user) —
        #    only every Nth iteration so we don't hog the I²C bus.
        if on_card_during_run is not None:
            card_poll_counter += 1
            if card_poll_counter >= CARD_POLL_EVERY:
                card_poll_counter = 0
                card = read_card_universal(wand, timeout_ms=20)
                if card is not None:
                    if on_card_during_run(card):
                        stop[0] = True
                        break

        # 2. Poll each rule's event. First rule to fire runs its body,
        #    others are skipped this iteration (sequential semantics).
        for idx, rule in enumerate(rules):
            if stop[0]: break
            event_op = rule['event']
            poller = POLLERS.get(event_op.get('op'))
            if poller is None:
                continue
            try:
                fired = poller(ctx, event_op.get('args', {}),
                               rule_states[idx])
            except Exception as e:
                print("poller error:", e)
                fired = False
            if fired:
                if on_rule_fire is not None:
                    try: on_rule_fire(idx)
                    except Exception as e: print("on_rule_fire err:", e)
                _run_body(rule['body'], ctx, ui=ui, rule_idx=idx)
                # Reset to all-dim after body completes
                if ui is not None:
                    try: ui.paint_running(rules, -1)
                    except Exception: pass
                break

        time.sleep_ms(loop_ms)

    # Safety: stop any running motors
    print("STOP card detected — stopping all motors")
    for slot, hub, info in connections:
        pid = info.get('product_id')
        if pid == DOUBLE_MOTOR:
            try:
                hub.motor_speed(MOTOR_BOTH, 0)
                hub.motor_stop(MOTOR_BOTH)
            except: pass
        elif pid == SINGLE_MOTOR:
            try:
                hub.motor_speed(PORT_SINGLE, 0)
                hub.motor_stop(PORT_SINGLE)
            except: pass