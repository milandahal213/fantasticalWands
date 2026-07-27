"""Helpers shared by behavior modules."""
import lego_ble as L


def find(devices, kind):
    """Return the first connected device of the given kind, or None."""
    for d in devices:
        if d.kind == kind:
            return d
    return None


def clamp(v, lo=-100, hi=100):
    return max(lo, min(hi, v))


def _ang_dist(a, b):
    """Smallest absolute distance between two angles on a 0–359 circle."""
    d = abs((a - b) % 360)
    return min(d, 360 - d)


class Swinger:
    """Sweep a single motor back and forth between -amp and +amp, through center.

    Call update(motor, amp, speed) every tick. `amp` is the half-swing in degrees
    and `speed` is 1–100. Both may change from tick to tick (that's how the
    color/joystick/light behaviors steer the swing) — the swing retargets when
    they do, and flips direction each time the shaft reaches an end. Because it
    forces the rotation sense, the shaft always passes through center rather than
    snapping around the back. Call reset() when the behavior stops.
    """
    TOL = 15          # degrees from the target that counts as "arrived"
    SPEED_STEP = 8    # min speed change (%) before re-issuing a move mid-swing

    def __init__(self):
        self.reset()

    def reset(self):
        self._dir = 1          # +1 heading toward +amp, -1 toward -amp
        self._amp = None       # last commanded amplitude
        self._speed = None     # last commanded speed
        self._started = False

    def update(self, motor, amp, speed):
        amp = max(0, int(amp))
        speed = max(1, min(100, int(speed)))
        if amp == 0:
            return
        goal = self._dir * amp
        pos = getattr(motor, "absolute_position", None)
        arrived = pos is not None and _ang_dist(pos, goal % 360) <= self.TOL
        if not self._started:
            self._send(motor, goal, speed, first=True)
        elif arrived:
            self._dir = -self._dir                     # reached an end → turn around
            self._send(motor, self._dir * amp, speed)
        elif amp != self._amp or abs(speed - self._speed) >= self.SPEED_STEP:
            self._send(motor, goal, speed)             # width/speed changed → refresh

    def _send(self, motor, goal, speed, first=False):
        if first:
            direction = L.MOTOR_DIR_SHORTEST           # unknown start pos: just get there
        else:
            # +goal reached by turning clockwise, -goal counter-clockwise, so the
            # shaft sweeps through 0 (center) rather than around the back.
            direction = L.MOTOR_DIR_CLOCKWISE if goal >= 0 else L.MOTOR_DIR_COUNTERCLOCKWISE
        motor.run_to_position(goal, speed=speed, direction=direction)
        self._amp = abs(goal)
        self._speed = speed
        self._started = True
