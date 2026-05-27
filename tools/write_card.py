# write_card.py — utility to write programming-card serials onto NFC tags.
#
# Cards: MIFARE Classic 1K, default key A = FF FF FF FF FF FF (blanks)
#
# Workflow:
#   1. Run this script.
#   2. Note the serial of the opcode you want (e.g. 9402 = 'move 2 steps').
#   3. Type the serial at the prompt.
#   4. Hold a blank MIFARE Classic card on the wand. The wand chirps
#      when written. The UID is printed so you can keep track.
#   5. Label the physical card with what it does.
#   6. Repeat. Type 'q' to quit.
#
# If a write fails with an auth error, the card is NOT using the default
# key. Either get truly-blank cards, or reformat the offending card with
# a separate tool.

from wand import Wand
from program_cards import OPCODES, list_opcodes, write_card_serial
import time

w = Wand()
time.sleep(0.5)

print("\n══════════════════════════════════════════════════════")
print(" Programming-card writer (MIFARE Classic 1K)")
print("══════════════════════════════════════════════════════")
list_opcodes()
print()

while True:
    try:
        ans = input("\nSerial to write (or 'l' to re-list, 'q' to quit): ").strip()
    except EOFError:
        break

    if not ans:           continue
    if ans in ('q', 'Q'): break
    if ans in ('l', 'L'): list_opcodes(); continue

    try:
        serial = int(ans)
    except ValueError:
        print("  Not a number.")
        continue

    opcode = OPCODES.get(serial)
    if opcode is None:
        print("  No such opcode. ('l' to re-list.)")
        continue

    print("  Writing: serial {} = '{}'".format(serial, opcode['name']))
    print("  Hold a blank MIFARE Classic 1K card on the wand now...")

    ok = False
    deadline = time.ticks_ms() + 15000   # 15s timeout
    last_attempt = 0
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        # Throttle attempts to ~3/sec so we don't hammer the I2C bus
        now = time.ticks_ms()
        if time.ticks_diff(now, last_attempt) < 350:
            time.sleep_ms(50); continue
        last_attempt = now

        if write_card_serial(w, serial):
            ok = True
            break

    if ok:
        print("  ✓ Written. (Label the card: '{}')".format(opcode['name']))
        w.beep(2000, 100)
    else:
        print("  ✗ Failed.")
        print("    Possible causes:")
        print("      - No card detected within 15s")
        print("      - Card uses a non-default key (not factory-blank)")
        print("      - Card is read-only or damaged")
        w.beep(400, 200)