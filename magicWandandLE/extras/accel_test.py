# accel_test.py — capture accelerometer readings so we can map tilt -> motor
# speed for advertise mode.
#
# Run it (from the REPL:  import accel_test) and tilt the wand slowly through
# its FULL range on each axis. It prints CSV to the serial console:
#
#     t_ms,x,y,z
#
# Select-all + copy the output and send it back — I'll turn the min/max range
# into the accel_to_sticks() mapping. It also prints a running min/max so you
# can eyeball the range live.
#
# Controls:
#   button tap  -> print + reset the min/max window (and beep)
#   Ctrl-C      -> stop and print the final min/max
#
# The motor speed curve you found (b5: 0x01 slow -> ~0x90 max -> tapers) is the
# OTHER half of the map; tell me the exact usable range and direction and I'll
# fold both together.

from wand import Wand
import time

RATE_MS = 100          # sample period (~10 Hz)


def main():
    w = Wand()
    acc = w.accel       # lazy-inits the LIS2DW12

    mn = [9.9, 9.9, 9.9]
    mx = [-9.9, -9.9, -9.9]

    def reset():
        for i in range(3):
            mn[i] = 9.9
            mx[i] = -9.9

    print("# tilt the wand through its full range on each axis")
    print("# button = reset min/max, Ctrl-C = stop")
    print("t_ms,x,y,z")

    n = 0
    try:
        while True:
            x, y, z = acc.read()
            v = (x, y, z)
            for i in range(3):
                if v[i] < mn[i]: mn[i] = v[i]
                if v[i] > mx[i]: mx[i] = v[i]

            print("{},{:+.3f},{:+.3f},{:+.3f}".format(time.ticks_ms(), x, y, z))

            n += 1
            if n % 20 == 0:      # every ~2 s, show the range so far
                print("# range  x[{:+.2f},{:+.2f}]  y[{:+.2f},{:+.2f}]  z[{:+.2f},{:+.2f}]".format(
                    mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]))

            if w.button_pressed():
                print("# --- min/max reset ---  x[{:+.2f},{:+.2f}] y[{:+.2f},{:+.2f}] z[{:+.2f},{:+.2f}]".format(
                    mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]))
                reset()
                w.beep(1500, 40)
                time.sleep_ms(300)

            time.sleep_ms(RATE_MS)

    except KeyboardInterrupt:
        print("# FINAL  x[{:+.2f},{:+.2f}]  y[{:+.2f},{:+.2f}]  z[{:+.2f},{:+.2f}]".format(
            mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]))
        print("# stopped")


main()
