"""Motor Knob — turn the DOUBLE motor by hand like a dial; the single motor
mirrors its angle. Uses the motor's built-in run-to-position, so the single
motor drives to the target and HOLDS there (the hub does the closed-loop) —
no software speed control, no drift.

Knob   = double motor (hand-turned, we read its position)
Follower = single motor (driven to match)
Swap the two find() lines to reverse the roles.
"""
from behaviors.util import find

STEP = 4      # only re-target when the knob has moved this many degrees


class MotorKnob:
    NAME = "Motor Knob"
    REQUIRED = ["single_motor", "double_motor"]

    def __init__(self):
        self.last = None

    def on_start(self, devices):
        self.last = None

    def tick(self, devices):
        knob = find(devices, "double_motor")       # hand-turned dial
        follower = find(devices, "single_motor")   # mirrors the angle
        if not knob or not follower:
            return
        pos = knob.pos_l                           # double motor's shaft angle
        if pos is None:
            return
        target = int(pos) % 360
        if self.last is None or abs(target - self.last) >= STEP:
            follower.run_to_position(target)       # go there and hold
            self.last = target

    def on_stop(self, devices):
        follower = find(devices, "single_motor")
        if follower:
            follower.stop()
