"""Simon Says — the sensor beeps out a growing color sequence; replay it by
presenting the colors in order. Right = the note; wrong = a low buzz + restart."""
import time

from behaviors.util import find


class SimonSays:
    NAME = "Simon Says (color memory)"
    REQUIRED = ["color_sensor"]

    COLORS = [1, 2, 3, 5]                       # red, yellow, blue, green (app ids)
    TONES = {1: 262, 2: 294, 3: 330, 5: 392}
    PLAY_GAP_MS = 600

    def __init__(self):
        self.seq = []
        self.phase = "play"     # "play" (show sequence) or "input" (user replays)
        self.idx = 0
        self.t = 0
        self.last_seen = None

    def on_start(self, devices):
        self.seq = []
        self._add()
        self.phase = "play"
        self.idx = 0
        self.t = time.ticks_ms()

    def _add(self):
        try:
            import random
            self.seq.append(self.COLORS[random.randrange(len(self.COLORS))])
        except Exception:
            self.seq.append(self.COLORS[len(self.seq) % len(self.COLORS)])

    def tick(self, devices):
        s = find(devices, "color_sensor")
        if not s:
            return
        now = time.ticks_ms()

        if self.phase == "play":
            if self.idx < len(self.seq):
                if time.ticks_diff(now, self.t) > self.PLAY_GAP_MS:
                    s.beep(frequency=self.TONES[self.seq[self.idx]], count=1)
                    self.idx += 1
                    self.t = now
            else:
                self.phase = "input"
                self.idx = 0
                self.last_seen = None
            return

        # input phase — watch for a new color and compare to the sequence
        c = s.color
        if c in (None, 0):
            self.last_seen = None          # allow re-showing the same color
            return
        if c == self.last_seen or c not in self.TONES:
            return
        self.last_seen = c
        if c == self.seq[self.idx]:
            s.beep(frequency=self.TONES[c], count=1)
            self.idx += 1
            if self.idx >= len(self.seq):  # round cleared -> grow + replay
                self._add()
                self.phase = "play"
                self.idx = 0
                self.t = now
        else:
            s.beep(frequency=150, count=3)  # wrong -> restart
            self.seq = []
            self._add()
            self.phase = "play"
            self.idx = 0
            self.t = now
