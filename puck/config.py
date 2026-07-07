"""
config.py — the ONLY file you edit per puck.

Flash every puck with the same code; give each one its identity + job here.
  PUCK_COLOR   : the color written on this puck's NFC card
  PUCK_SERIAL  : the serial written on this puck's NFC card
  BEHAVIOR     : which behavior to run (a key in behaviors/__init__.py BEHAVIORS)
"""

PUCK_COLOR = "pink"          # magenta/pink, purple, blue, azure, teal,
                            # green, yellow, orange, red, white
PUCK_SERIAL = 1005
BEHAVIOR = "tank_drive"     # tank_drive, arcade_drive, light_theremin, spin
