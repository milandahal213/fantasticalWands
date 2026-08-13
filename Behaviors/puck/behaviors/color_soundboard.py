"""Color Soundboard — each color the sensor sees plays a different note on the
sensor's own beeper. Wave colored cards past it to make a tune."""
from behaviors.util import find


class ColorSoundboard:
    NAME = "Color Soundboard"
    REQUIRED = ["color_sensor"]

    # app color id -> frequency (roughly C4..D5)
    TONES = {1: 262, 2: 294, 3: 330, 5: 392, 6: 440, 8: 494, 9: 523, 10: 587}

    def __init__(self):
        self.last = None

    def tick(self, devices):
        s = find(devices, "color_sensor")
        if not s:
            return
        c = s.color
        if c is not None and c != self.last:
            self.last = c
            f = self.TONES.get(c)
            if f:
                s.beep(frequency=f, count=1)
